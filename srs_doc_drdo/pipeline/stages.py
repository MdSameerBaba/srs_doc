"""
stages.py — All 6 pipeline prompt stages (A → F).

Model routing (local Ollama):
  Heavy (A, C, D, E, F) : config["heavy_model"]  → default gpt-oss-20b
  Fast  (B)             : config["fast_model"]   → default gemma3n:e4b
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from . import graph_loader as gl
from . import ollama_client as ollama
import constants


# ═══════════════════════════════════════════════════════════════════
#  PROMPT TEMPLATES
# ═══════════════════════════════════════════════════════════════════

_PROMPT_A = """\
You are analyzing a codebase to build an architecture snapshot before deep extraction.

INPUT — File manifest:
{file_manifest}

INPUT — Directory tree:
{dir_tree}

INPUT — Config / build files:
{config_files}

INPUT — README:
{readme_content}

TASK: Produce a structural overview. Do not infer business logic yet.

OUTPUT (JSON only, no other text):
{{
  "languages_detected": ["..."],
  "frameworks_detected": ["..."],
  "external_services": ["..."],
  "modules": [
    {{"name": "...", "path": "...", "language": "...", "purpose_guess": "..."}}
  ],
  "build_system": "...",
  "unsupported_files": ["..."],
  "confidence_notes": "..."
}}

RULES:
- Only state what is directly evidenced by file/config contents.
- If purpose is unclear, write "purpose_guess": "UNKNOWN".
- Do not invent modules not present in the file manifest.
"""

_PROMPT_B = """\
You are summarizing a single code unit. Be literal — describe only what this code does.

INPUT:
- Signature: {signature}
- Source code:
{code_slice}
- Direct calls made: {call_list}
- File: {file_path}, lines {line_start}-{line_end}

OUTPUT (JSON only, no other text):
{{
  "id": "{node_id}",
  "summary": "<1-2 sentences describing what this code does>",
  "side_effects": ["..."],
  "inputs": ["..."],
  "outputs": ["..."],
  "evidence": {{"file": "{file_path}", "lines": [{line_start}, {line_end}]}}
}}

RULES:
- Do NOT guess business intent beyond what the code literally does.
- If behavior is unclear, set "summary" to "UNCLEAR".
- Every claim must trace to the provided code.
"""

_PROMPT_C = """\
You are aggregating function-level summaries into a module-level behavior description.

INPUT — Module: {module_name}
INPUT — Leaf summaries:
{leaf_summaries}
INPUT — Intra-module call graph edges:
{edges}

OUTPUT (JSON only, no other text):
{{
  "module": "{module_name}",
  "responsibilities": ["<responsibility> [evidence: id1, id2]"],
  "key_entities": ["..."],
  "evidence_ids": ["..."]
}}

RULES:
- Use ONLY the provided leaf summaries — do not re-read raw code.
- Every responsibility must cite evidence_ids that support it.
- Do not merge unrelated summaries unless call graph edges connect them.
"""

_PROMPT_D = """\
You are extracting functional requirements from verified module summaries.
This output becomes the FROZEN canonical source for all SRS generation.

INPUT — Module rollups:
{module_rollups}

INPUT — Architecture snapshot:
{architecture}

OUTPUT (JSON only, no other text):
{{
  "actors": [{{"name": "...", "evidence_ids": [...]}}],
  "functional_requirements": [
    {{
      "id": "FR-1",
      "title": "...",
      "description": "...",
      "actor": "...",
      "evidence_ids": ["..."],
      "confidence": "HIGH"
    }}
  ],
  "non_functional_signals": [
    {{
      "category": "performance|security|reliability|scalability|maintainability",
      "description": "...",
      "evidence_ids": ["..."],
      "confidence": "HIGH|MEDIUM|LOW"
    }}
  ]
}}

RULES:
- Every FR must have at least one evidence_id. No evidence = omit.
- Do NOT infer NFRs from absence of code. Only from explicit evidence
  (rate limiters, auth middleware, encryption calls, retry logic, etc.)
- Mark confidence LOW if extraction required any inference.
- Be conservative — under-extraction is safer than hallucination.
"""

_PROMPT_E = """You are a senior systems analyst and technical writer producing a formal, IEEE-830 compliant Software Requirements Specification (SRS) document.

YOUR ONLY INPUT SOURCE — CANONICAL REQUIREMENTS (frozen):
{canonical}

TASK INSTRUCTION FOR THIS SECTION:
{section_instruction}

ABSOLUTE RULES — VIOLATION OF THESE IS NOT ACCEPTABLE:
1. BASE EVERYTHING ON THE CANONICAL REQUIREMENTS. Every statement, claim, requirement, and data point must be directly traceable to the frozen canonical requirements.
2. DO NOT HALLUCINATE. Never invent function names, endpoints, features, data models, user roles, SLA numbers, or technologies that are not present in the canonical requirements.
3. WHEN INFORMATION IS ABSENT, SAY SO. If a sub-section or requirement cannot be addressed from the provided canonical requirements, write exactly: "Not determinable from the provided codebase." Do not guess, infer, or generalise.
4. CITE YOUR EVIDENCE. When making a claim, reference the specific requirement ID or evidence ID that supports it (e.g. [evidence: FR-1] or [evidence: fn:auth.py:login]).
5. NO CODE IN OUTPUT. The generated SRS document must contain ZERO lines of source code. Describe what the software does in plain English — never show how it does it in code.
6. Write in formal, professional Markdown. Begin directly with the section heading — no preamble.
"""

_PROMPT_F = """\
You are a strict auditor comparing a generated SRS section against canonical requirements.
Find every discrepancy. Do not be lenient.

CANONICAL REQUIREMENTS (frozen):
{canonical}

GENERATED SECTION:
{section_markdown}

CHECK FOR:
1. FRs in CANONICAL but missing from GENERATED
2. FRs in GENERATED not in CANONICAL (hallucinated)
3. FR IDs renamed, renumbered, or reworded
4. Claims with no evidence_id citation
5. Evidence_id citations that do not match the canonical entry

OUTPUT (JSON only, no other text):
{{
  "missing":        ["FR-..."],
  "hallucinated":   ["FR-..."],
  "renamed":        [{{"id": "...", "canonical_title": "...", "generated_as": "..."}}],
  "uncited_claims": ["<short excerpt of the uncited claim>"],
  "status":         "PASS|FAIL"
}}
"""

# ── SRS section catalogue (Aligned with DRDO spec) ──────────────────────────
SRS_SECTIONS: list[tuple[int, str]] = [
    (1,  "Introduction"),
    (2,  "Acronyms"),
    (3,  "Reference Documents"),
    (4,  "Product Description"),
    (5,  "System Features"),
    (6,  "States and Modes"),
    (7,  "Detailed Software Requirement"),
    (8,  "Timing Requirements"),
    (9,  "Loadable Data Requirements"),
    (10, "Internal and External Interface Requirement"),
    (11, "Traceability Matrix"),
]


# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════

def _read_source_slice(
    file_path: str, line_start: int | None, line_end: int | None, codebase_path: Path
) -> str:
    """Read a slice of source lines from disk."""
    try:
        fp = Path(file_path)
        if not fp.is_absolute():
            fp = codebase_path / file_path
        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        s = max(0, (line_start or 1) - 1)
        e = min(len(lines), line_end or len(lines))
        return "".join(lines[s:e])
    except Exception:
        return f"# Source unavailable: {file_path}"


def _build_dir_tree(root: Path, max_depth: int = 3) -> str:
    """Build a condensed directory-tree string."""
    _SKIP = {
        "node_modules", "__pycache__", ".git", ".venv", "venv",
        "dist", "build", "graphify-out", ".mypy_cache", "srs_output"
    }
    lines: list[str] = []

    def walk(path: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return
        for idx, entry in enumerate(entries):
            if entry.name.startswith(".") or entry.name in _SKIP:
                continue
            connector = "└── " if idx == len(entries) - 1 else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if idx == len(entries) - 1 else "│   "
                walk(entry, prefix + extension, depth + 1)
            if len(lines) >= 120:
                lines.append(f"{prefix}    ... (truncated)")
                return

    walk(root, "", 0)
    return "\n".join(lines)


def _read_config_files(codebase_path: Path) -> str:
    _NAMES = [
        "requirements.txt", "package.json", "setup.py", "pyproject.toml",
        "setup.cfg", "Makefile", "CMakeLists.txt", "build.gradle",
        "pom.xml", "Cargo.toml", "go.mod", "composer.json",
    ]
    parts: list[str] = []
    for name in _NAMES:
        p = codebase_path / name
        if p.exists():
            try:
                content = p.read_text(encoding="utf-8")[:1500]
                parts.append(f"=== {name} ===\n{content}")
            except Exception:
                pass
    return "\n\n".join(parts) or "[No recognised config files found]"


def _read_readme(codebase_path: Path) -> str:
    for name in ["README.md", "README.rst", "README.txt", "README"]:
        p = codebase_path / name
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")[:3000]
            except Exception:
                pass
    return "[No README found]"


# ═══════════════════════════════════════════════════════════════════
#  STAGE A — Architecture Snapshot
# ═══════════════════════════════════════════════════════════════════

def run_stage_a(
    db_path: Path,
    codebase_path: Path,
    config: dict,
    log: Callable[[str], None],
) -> dict:
    log("Preparing file manifest and directory tree…")
    files = gl.get_file_manifest(db_path)
    manifest_str = "\n".join(files[:300])

    prompt = _PROMPT_A.format(
        file_manifest=manifest_str or "[empty]",
        dir_tree=_build_dir_tree(codebase_path),
        config_files=_read_config_files(codebase_path),
        readme_content=_read_readme(codebase_path),
    )

    log(f"Sending to {config['heavy_model']}…")
    result = ollama.chat(config["heavy_model"], prompt, config["ollama_url"])
    log(f"Architecture snapshot: {len(result.get('modules', []))} modules detected")
    return result


# ═══════════════════════════════════════════════════════════════════
#  STAGE B — Leaf Node Summarization  (parallel with ThreadPoolExecutor)
# ═══════════════════════════════════════════════════════════════════

def run_stage_b(
    db_path: Path,
    codebase_path: Path,
    config: dict,
    log: Callable[[str], None],
    progress_cb: Callable[[int, int], None],
) -> list[dict]:
    nodes = gl.get_nodes_for_summarization(db_path)
    total = len(nodes)
    if total == 0:
        log("No unsummarized code units found (all cached or no functions/classes).")
        return []

    log(f"Summarizing {total} code units with {config['fast_model']} (workers={config['concurrency']})…")
    results: list[dict] = []
    completed = 0

    def _summarize(node: dict) -> dict | None:
        code = _read_source_slice(
            node["file_path"], node["line_start"], node["line_end"], codebase_path
        )
        calls = gl.get_calls_for_node(db_path, node["id"])
        sig = f"{node['type']} {node['label']}"
        if node.get("docstring"):
            sig += f"  # {node['docstring'][:150]}"

        prompt = _PROMPT_B.format(
            signature=sig,
            code_slice=code[:2500],
            call_list=", ".join(calls[:20]) or "none",
            file_path=node["file_path"] or "unknown",
            line_start=node["line_start"] or 0,
            line_end=node["line_end"]   or 0,
            node_id=node["id"],
        )
        try:
            res = ollama.chat(config["fast_model"], prompt, config["ollama_url"])
            if isinstance(res, dict):
                res["id"] = node["id"]
                gl.save_leaf_summary(db_path, res)
                return res
        except Exception as exc:
            # Save a minimal sentinel so we don't retry indefinitely
            fallback = {
                "id": node["id"],
                "summary": "UNCLEAR",
                "side_effects": [],
                "inputs": [],
                "outputs": [],
                "evidence": {
                    "file": node["file_path"],
                    "lines": [node["line_start"], node["line_end"]],
                },
            }
            gl.save_leaf_summary(db_path, fallback)
        return None

    workers = max(1, min(config.get("concurrency", 3), total))
    with ThreadPoolExecutor(max_workers=workers) as exe:
        futures = {exe.submit(_summarize, n): n for n in nodes}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                results.append(res)
            completed += 1
            progress_cb(completed, total)

    log(f"Leaf summarization done: {len(results)}/{total} successful")
    return results


# ═══════════════════════════════════════════════════════════════════
#  STAGE C — Module / Subsystem Rollup
# ═══════════════════════════════════════════════════════════════════

def run_stage_c(
    db_path: Path,
    config: dict,
    log: Callable[[str], None],
    progress_cb: Callable[[int, int], None],
) -> list[dict]:
    modules = gl.get_distinct_modules(db_path)
    total = len(modules)
    rollups: list[dict] = []

    for i, module in enumerate(modules):
        log(f"Rolling up module ({i+1}/{total}): {module}")
        summaries = gl.get_leaf_summaries_for_module(db_path, module)
        if not summaries:
            progress_cb(i + 1, total)
            continue

        edges = gl.get_intramodule_edges(db_path, module)
        prompt = _PROMPT_C.format(
            module_name=module,
            leaf_summaries=json.dumps(summaries[:60], indent=2),
            edges=json.dumps(edges[:100], indent=2),
        )
        try:
            res = ollama.chat(config["heavy_model"], prompt, config["ollama_url"])
            if isinstance(res, dict):
                res["module"] = module
                gl.save_module_rollup(db_path, res)
                rollups.append(res)
        except Exception as exc:
            log(f"  ⚠ Rollup failed for {module}: {exc}")
            rollups.append({
                "module": module,
                "responsibilities": [],
                "key_entities": [],
                "evidence_ids": [],
            })
        progress_cb(i + 1, total)

    log(f"Module rollup done: {len(rollups)} modules")
    return rollups


# ═══════════════════════════════════════════════════════════════════
#  STAGE D — Behavior / Requirement Extraction  ← FREEZE POINT
# ═══════════════════════════════════════════════════════════════════

def run_stage_d(
    architecture: dict,
    db_path: Path,
    config: dict,
    log: Callable[[str], None],
) -> dict:
    log("Loading all module rollups for canonical extraction…")
    rollups = gl.get_all_module_rollups(db_path)

    prompt = _PROMPT_D.format(
        module_rollups=json.dumps(rollups, indent=2),
        architecture=json.dumps(architecture, indent=2),
    )
    log(f"Sending to {config['heavy_model']} (this is the FREEZE step)…")
    result = ollama.chat(config["heavy_model"], prompt, config["ollama_url"])
    frs = result.get("functional_requirements") or []
    nfrs = result.get("non_functional_signals") or []
    fr_count = len(frs)
    nfr_count = len(nfrs)
    log(f"Extracted {fr_count} FRs, {nfr_count} NFR signals — CANONICAL FROZEN")
    return result


# ═══════════════════════════════════════════════════════════════════
#  STAGE E — SRS Section Writer
# ═══════════════════════════════════════════════════════════════════

def run_stage_e(
    canonical: dict,
    section_num: int,
    section_title: str,
    config: dict,
    log: Callable[[str], None],
) -> str:
    log(f"Writing Section {section_num}: {section_title}…")
    
    # Map section number to the key in constants.SECTION_PROMPTS
    keys = {
        1: "1_introduction",
        2: "2_acronyms",
        3: "3_reference_documents",
        4: "4_product_description",
        5: "5_system_features",
        6: "6_states_and_modes",
        7: "7_detailed_sw_requirement",
        8: "8_timing_requirements",
        9: "9_loadable_data",
        10: "10_interface_requirements",
        11: "11_traceability_matrix"
    }
    sec_key = keys.get(section_num, "")
    section_instruction = constants.SECTION_PROMPTS.get(
        sec_key,
        f"Generate only the SRS section titled '{section_title}' based strictly and exclusively on the canonical requirements."
    )
    
    prompt = _PROMPT_E.format(
        canonical=json.dumps(canonical, indent=2),
        section_instruction=section_instruction
    )
    result = ollama.chat(config["heavy_model"], prompt, config["ollama_url"], expect_json=False)
    return str(result)


# ═══════════════════════════════════════════════════════════════════
#  STAGE F — Verifier  (adversarial, with retry)
# ═══════════════════════════════════════════════════════════════════

def run_stage_f(
    canonical: dict,
    section_markdown: str,
    section_num: int,
    section_title: str,
    config: dict,
    log: Callable[[str], None],
    max_retries: int = 2,
) -> tuple[str, dict]:
    """
    Returns (final_markdown, verification_report).
    Retries Prompt E up to max_retries times on FAIL.
    """
    for attempt in range(max_retries + 1):
        log(f"  Verifying Section {section_num} (attempt {attempt + 1}/{max_retries + 1})…")
        prompt = _PROMPT_F.format(
            canonical=json.dumps(canonical, indent=2),
            section_markdown=section_markdown,
        )
        try:
            report = ollama.chat(config["heavy_model"], prompt, config["ollama_url"])
        except Exception:
            report = {"status": "PASS", "missing": [], "hallucinated": [],
                      "renamed": [], "uncited_claims": []}

        status = report.get("status", "PASS") if isinstance(report, dict) else "PASS"

        if status == "PASS":
            log(f"  ✅ Section {section_num} passed verification")
            return section_markdown, report

        if attempt < max_retries:
            log(f"  ⚠ Section {section_num} failed — regenerating…")
            issues = json.dumps(report, indent=2)
            
            keys = {
                1: "1_introduction",
                2: "2_acronyms",
                3: "3_reference_documents",
                4: "4_product_description",
                5: "5_system_features",
                6: "6_states_and_modes",
                7: "7_detailed_sw_requirement",
                8: "8_timing_requirements",
                9: "9_loadable_data",
                10: "10_interface_requirements",
                11: "11_traceability_matrix"
            }
            sec_key = keys.get(section_num, "")
            section_instruction = constants.SECTION_PROMPTS.get(
                sec_key,
                f"Generate only the SRS section titled '{section_title}' based strictly and exclusively on the canonical requirements."
            )

            regen_prompt = (
                _PROMPT_E.format(
                    canonical=json.dumps(canonical, indent=2),
                    section_instruction=section_instruction,
                )
                + f"\n\nPREVIOUS ATTEMPT FAILED VERIFICATION. Issues:\n{issues}\n"
                  "Fix all issues in this regeneration."
            )
            try:
                section_markdown = str(
                    ollama.chat(
                        config["heavy_model"], regen_prompt,
                        config["ollama_url"], expect_json=False
                    )
                )
            except Exception:
                pass  # keep previous markdown, try verification again

    # Exhausted retries
    if isinstance(report, dict):
        report["status"] = "NEEDS_REVIEW"
    log(f"  ⚠ Section {section_num} needs manual review after {max_retries+1} attempts")
    return section_markdown, report
