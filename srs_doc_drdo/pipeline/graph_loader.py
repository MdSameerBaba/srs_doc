"""
graph_loader.py
Loads graphifyy's graph.json into a local SQLite database.

graphifyy graph.json structure:
  {
    "nodes": [ { "id", "label"/"name", "type", "file"/"file_path",
                 "line_start"/"lineStart", "line_end"/"lineEnd",
                 "docstring", "sha256"/"hash", ...} ],
    "links": [ { "source", "target", "type"/"rel_type",
                 "confidence", "score"/"conf_score" } ]
  }
"""

import json
import sqlite3
from pathlib import Path
from typing import Callable, Optional
from contextlib import contextmanager


# ─────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────

_SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS nodes (
    id          TEXT PRIMARY KEY,
    label       TEXT,
    type        TEXT,
    file_path   TEXT,
    line_start  INTEGER,
    line_end    INTEGER,
    docstring   TEXT,
    sha256      TEXT,
    raw_json    TEXT
);

CREATE TABLE IF NOT EXISTS edges (
    rowid       INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    target      TEXT NOT NULL,
    rel_type    TEXT,
    confidence  TEXT DEFAULT 'EXTRACTED',
    conf_score  REAL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS leaf_summaries (
    node_id      TEXT PRIMARY KEY,
    summary      TEXT,
    side_effects TEXT,   -- JSON array
    inputs       TEXT,   -- JSON array
    outputs      TEXT,   -- JSON array
    evidence     TEXT,   -- JSON object
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS module_rollups (
    module            TEXT PRIMARY KEY,
    responsibilities  TEXT,   -- JSON array
    key_entities      TEXT,   -- JSON array
    evidence_ids      TEXT,   -- JSON array
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_nodes_type   ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_file   ON nodes(file_path);
CREATE INDEX IF NOT EXISTS idx_edges_src    ON edges(source);
CREATE INDEX IF NOT EXISTS idx_edges_tgt    ON edges(target);
"""


# ─────────────────────────────────────────────────────────────
# Loader
# ─────────────────────────────────────────────────────────────

def load_graph(graph_path: Path, db_path: Path) -> dict:
    """
    Parse graph.json produced by graphifyy and persist into SQLite.
    Returns a stats dict: { nodes, edges, type_counts, files }.
    """
    with open(graph_path, "r", encoding="utf-8") as fh:
        graph: dict = json.load(fh)

    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.executescript(_SCHEMA)

    raw_nodes: list = graph.get("nodes", [])
    raw_links: list = graph.get("links", graph.get("edges", []))

    # ── nodes ──────────────────────────────────────────────
    node_count = 0
    for n in raw_nodes:
        file_path = (
            n.get("file")
            or n.get("file_path")
            or n.get("filepath")
            or n.get("source_file")
            or ""
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO nodes
                (id, label, type, file_path, line_start, line_end,
                 docstring, sha256, raw_json)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                n.get("id", ""),
                n.get("label") or n.get("name", ""),
                n.get("type", "unknown"),
                file_path,
                n.get("line_start") or n.get("lineStart"),
                n.get("line_end")   or n.get("lineEnd"),
                n.get("docstring", ""),
                n.get("sha256")  or n.get("hash", ""),
                json.dumps(n),
            ),
        )
        node_count += 1

    # ── edges ──────────────────────────────────────────────
    edge_count = 0
    for lnk in raw_links:
        confidence = lnk.get("confidence", "EXTRACTED")
        default_score = 1.0 if confidence == "EXTRACTED" else 0.5
        conn.execute(
            """
            INSERT INTO edges (source, target, rel_type, confidence, conf_score)
            VALUES (?,?,?,?,?)
            """,
            (
                lnk.get("source", ""),
                lnk.get("target", ""),
                lnk.get("type") or lnk.get("rel_type", "calls"),
                confidence,
                lnk.get("score") or lnk.get("conf_score", default_score),
            ),
        )
        edge_count += 1

    conn.commit()

    # ── stats ──────────────────────────────────────────────
    type_counts: dict = {}
    for row in conn.execute(
        "SELECT type, COUNT(*) FROM nodes GROUP BY type"
    ):
        type_counts[row[0]] = row[1]

    file_count = conn.execute(
        "SELECT COUNT(DISTINCT file_path) FROM nodes WHERE file_path != ''"
    ).fetchone()[0]

    conn.close()
    return {
        "nodes": node_count,
        "edges": edge_count,
        "type_counts": type_counts,
        "files": file_count,
    }


# ─────────────────────────────────────────────────────────────
# Query helpers
# ─────────────────────────────────────────────────────────────

@contextmanager
def _conn(db_path: Path):
    c = sqlite3.connect(str(db_path), timeout=30.0)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()


def get_file_manifest(db_path: Path) -> list[str]:
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT DISTINCT file_path FROM nodes WHERE file_path != '' ORDER BY file_path"
        ).fetchall()
    return [r["file_path"] for r in rows]


def get_nodes_for_summarization(db_path: Path) -> list[dict]:
    """Return function/class nodes not yet in leaf_summaries."""
    with _conn(db_path) as c:
        rows = c.execute(
            """
            SELECT n.id, n.label, n.type, n.file_path,
                   n.line_start, n.line_end, n.docstring
            FROM   nodes n
            LEFT   JOIN leaf_summaries ls ON n.id = ls.node_id
            WHERE  n.type IN ('function','class','method','constructor')
            AND    ls.node_id IS NULL
            ORDER  BY n.file_path, n.line_start
            """
        ).fetchall()
    return [dict(r) for r in rows]


def get_calls_for_node(db_path: Path, node_id: str) -> list[str]:
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT target FROM edges WHERE source = ? AND rel_type = 'calls'",
            (node_id,),
        ).fetchall()
    return [r["target"] for r in rows]


def save_leaf_summary(db_path: Path, summary: dict) -> None:
    with _conn(db_path) as c:
        c.execute(
            """
            INSERT OR REPLACE INTO leaf_summaries
                (node_id, summary, side_effects, inputs, outputs, evidence)
            VALUES (?,?,?,?,?,?)
            """,
            (
                summary.get("id", ""),
                summary.get("summary", ""),
                json.dumps(summary.get("side_effects", [])),
                json.dumps(summary.get("inputs", [])),
                json.dumps(summary.get("outputs", [])),
                json.dumps(summary.get("evidence", {})),
            ),
        )


def get_all_leaf_summaries(db_path: Path) -> list[dict]:
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT node_id, summary, side_effects, inputs, outputs, evidence FROM leaf_summaries"
        ).fetchall()
    return [
        {
            "id":           r["node_id"],
            "summary":      r["summary"],
            "side_effects": json.loads(r["side_effects"] or "[]"),
            "inputs":       json.loads(r["inputs"]       or "[]"),
            "outputs":      json.loads(r["outputs"]      or "[]"),
            "evidence":     json.loads(r["evidence"]     or "{}"),
        }
        for r in rows
    ]


def get_distinct_modules(db_path: Path) -> list[str]:
    """Return unique module names derived from file paths."""
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT DISTINCT file_path FROM nodes WHERE file_path != '' ORDER BY file_path"
        ).fetchall()
    seen: set = set()
    modules: list = []
    for r in rows:
        stem = Path(r["file_path"]).stem
        if stem not in seen:
            seen.add(stem)
            modules.append(stem)
    return modules


def get_leaf_summaries_for_module(db_path: Path, module_stem: str) -> list[dict]:
    with _conn(db_path) as c:
        rows = c.execute(
            """
            SELECT ls.node_id, ls.summary, ls.side_effects,
                   ls.inputs, ls.outputs, ls.evidence
            FROM   leaf_summaries ls
            JOIN   nodes n ON ls.node_id = n.id
            WHERE  n.file_path LIKE ? OR n.file_path LIKE ?
            """,
            (f"%/{module_stem}.py", f"%\\{module_stem}.py"),
        ).fetchall()
        # Also try bare filename
        if not rows:
            rows = c.execute(
                """
                SELECT ls.node_id, ls.summary, ls.side_effects,
                       ls.inputs, ls.outputs, ls.evidence
                FROM   leaf_summaries ls
                JOIN   nodes n ON ls.node_id = n.id
                WHERE  n.file_path LIKE ?
                """,
                (f"%{module_stem}%",),
            ).fetchall()
    return [
        {
            "id":           r["node_id"],
            "summary":      r["summary"],
            "side_effects": json.loads(r["side_effects"] or "[]"),
            "inputs":       json.loads(r["inputs"]       or "[]"),
            "outputs":      json.loads(r["outputs"]      or "[]"),
            "evidence":     json.loads(r["evidence"]     or "{}"),
        }
        for r in rows
    ]


def get_intramodule_edges(db_path: Path, module_stem: str) -> list[dict]:
    with _conn(db_path) as c:
        # Try matching exact python file stems first to prevent false connections between files with similar names
        rows = c.execute(
            """
            SELECT e.source, e.target, e.rel_type
            FROM   edges e
            JOIN   nodes ns ON e.source = ns.id
            JOIN   nodes nt ON e.target = nt.id
            WHERE  (ns.file_path LIKE ? OR ns.file_path LIKE ? OR ns.file_path = ?)
            AND    (nt.file_path LIKE ? OR nt.file_path LIKE ? OR nt.file_path = ?)
            """,
            (
                f"%/{module_stem}.py", f"%\\{module_stem}.py", f"{module_stem}.py",
                f"%/{module_stem}.py", f"%\\{module_stem}.py", f"{module_stem}.py"
            ),
        ).fetchall()
        
        if not rows:
            # Fallback to general substring match if no exact python file matches exist
            rows = c.execute(
                """
                SELECT e.source, e.target, e.rel_type
                FROM   edges e
                JOIN   nodes ns ON e.source = ns.id
                JOIN   nodes nt ON e.target = nt.id
                WHERE  ns.file_path LIKE ?
                AND    nt.file_path LIKE ?
                """,
                (f"%{module_stem}%", f"%{module_stem}%"),
            ).fetchall()
    return [{"source": r["source"], "target": r["target"], "type": r["rel_type"]} for r in rows]


def save_module_rollup(db_path: Path, rollup: dict) -> None:
    with _conn(db_path) as c:
        c.execute(
            """
            INSERT OR REPLACE INTO module_rollups
                (module, responsibilities, key_entities, evidence_ids)
            VALUES (?,?,?,?)
            """,
            (
                rollup.get("module", ""),
                json.dumps(rollup.get("responsibilities", [])),
                json.dumps(rollup.get("key_entities", [])),
                json.dumps(rollup.get("evidence_ids", [])),
            ),
        )


def get_all_module_rollups(db_path: Path) -> list[dict]:
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT module, responsibilities, key_entities, evidence_ids FROM module_rollups"
        ).fetchall()
    return [
        {
            "module":           r["module"],
            "responsibilities": json.loads(r["responsibilities"] or "[]"),
            "key_entities":     json.loads(r["key_entities"]     or "[]"),
            "evidence_ids":     json.loads(r["evidence_ids"]     or "[]"),
        }
        for r in rows
    ]
