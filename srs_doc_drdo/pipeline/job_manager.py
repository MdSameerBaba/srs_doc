"""
job_manager.py — Multi-project background job runner, job queue, and persistent state manager.

Features:
  - Each upload creates an isolated job directory: srs_output/jobs/<job_id>/
  - Runs hands-free background thread: Stage 1-4 -> Auto-Freeze -> Stage E/F -> Section 11 -> Assembly
  - Multi-job queue allows running multiple archives in parallel or sequentially.
  - Persistent on disk: page refresh / tab closure does NOT disrupt running jobs.
"""

import os
import io
import json
import time
import zipfile
import tarfile
import threading
import traceback
from pathlib import Path
from datetime import datetime

from helpers import extract_zip, extract_tar, run_pure_python_extractor, resolve_codebase_path
from pipeline import graph_loader as gl
from pipeline import stages
from pipeline import assembler
from pipeline import ollama_client as _ollama_client

BASE_JOBS_DIR = Path("srs_output/jobs")
MANIFEST_PATH = BASE_JOBS_DIR / "job_manifest.json"

_manager_lock = threading.Lock()


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_job_system():
    BASE_JOBS_DIR.mkdir(parents=True, exist_ok=True)
    if not MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)


def list_all_jobs() -> list[dict]:
    """Return all jobs sorted by creation time descending."""
    init_job_system()
    with _manager_lock:
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                job_ids = json.load(f)
        except Exception:
            job_ids = []

    jobs = []
    for jid in job_ids:
        info_path = BASE_JOBS_DIR / jid / "job_info.json"
        if info_path.exists():
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    info = json.load(f)
                    jobs.append(info)
            except Exception:
                pass
    jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return jobs


def get_job_info(job_id: str) -> dict | None:
    info_path = BASE_JOBS_DIR / job_id / "job_info.json"
    if info_path.exists():
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def update_job_info(job_id: str, updates: dict):
    with _manager_lock:
        info_path = BASE_JOBS_DIR / job_id / "job_info.json"
        if info_path.exists():
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    info = json.load(f)
                info.update(updates)
                info["updated_at"] = _now_str()
                with open(info_path, "w", encoding="utf-8") as f:
                    json.dump(info, f, indent=2)
            except Exception:
                pass


def add_job_log(job_id: str, message: str):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] {message}"
    with _manager_lock:
        info_path = BASE_JOBS_DIR / job_id / "job_info.json"
        if info_path.exists():
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    info = json.load(f)
                logs = info.get("logs", [])
                logs.append(entry)
                info["logs"] = logs
                info["updated_at"] = _now_str()
                with open(info_path, "w", encoding="utf-8") as f:
                    json.dump(info, f, indent=2)
            except Exception:
                pass


def create_job(
    archive_name: str,
    archive_bytes: bytes,
    include_extensions: list[str],
    config: dict,
) -> str:
    """Create a new job, save bytes & metadata, and enqueue background execution."""
    init_job_system()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_name = Path(archive_name).stem.replace(" ", "_").replace("-", "_")
    job_id = f"JOB_{timestamp}_{clean_name}"
    job_dir = BASE_JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save raw archive
    archive_path = job_dir / archive_name
    archive_path.write_bytes(archive_bytes)

    job_info = {
        "job_id": job_id,
        "archive_name": archive_name,
        "clean_project_name": clean_name,
        "created_at": _now_str(),
        "updated_at": _now_str(),
        "status": "QUEUED",
        "progress_pct": 0,
        "current_stage": "Queued",
        "logs": [f"[{datetime.now().strftime('%H:%M:%S')}] Job created and queued for processing."],
        "include_extensions": include_extensions,
        "config": config,
        "stats": {},
        "error": None,
        "srs_sections": {},
        "verification_reports": {},
        "full_srs_doc": "",
    }

    info_path = job_dir / "job_info.json"
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(job_info, f, indent=2)

    # Register in manifest
    with _manager_lock:
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            manifest = []
        manifest.append(job_id)
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    # Launch background runner thread
    t = threading.Thread(target=_run_job_pipeline, args=(job_id, archive_path), daemon=True)
    t.start()

    return job_id


def delete_job(job_id: str):
    """Delete a job directory cleanly and remove from manifest."""
    init_job_system()
    job_dir = BASE_JOBS_DIR / job_id
    if job_dir.exists():
        for root, dirs, files in os.walk(job_dir, topdown=False):
            for name in files:
                p = Path(root) / name
                try:
                    os.chmod(p, 0o777)
                    p.unlink()
                except Exception:
                    pass
            for name in dirs:
                p = Path(root) / name
                try:
                    os.chmod(p, 0o777)
                    p.rmdir()
                except Exception:
                    pass
        try:
            job_dir.rmdir()
        except Exception:
            pass

    with _manager_lock:
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            manifest = [j for j in manifest if j != job_id]
            with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
        except Exception:
            pass


def _run_job_pipeline(job_id: str, archive_path: Path):
    """Hands-free background pipeline execution."""
    job_dir = BASE_JOBS_DIR / job_id
    info = get_job_info(job_id)
    if not info:
        return

    config = info.get("config", {})
    incl_list = info.get("include_extensions", [])
    project_name = info.get("clean_project_name", "Project")

    # Wire LLM Provider
    _ollama_client.PROVIDER = config.get("llm_provider", "ollama")
    _ollama_client.API_KEY = config.get("gemini_api_key", "")

    update_job_info(job_id, {"status": "RUNNING", "current_stage": "Extracting Codebase & Building Graph", "progress_pct": 5})
    add_job_log(job_id, "🚀 Starting background pipeline execution...")

    db_path = job_dir / "srs_graph.db"
    canonical_path = job_dir / "canonical.json"
    extracted_dir = job_dir / "extracted_codebase"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    try:
        # ── STEP 1: Archive Extraction & AST Graph Ingestion ──
        add_job_log(job_id, "Extracting project archive to disk...")
        if archive_path.name.lower().endswith(".zip"):
            with zipfile.ZipFile(archive_path, 'r') as z:
                z.extractall(extracted_dir)
        else:
            with tarfile.open(name=archive_path, mode="r:*") as t:
                t.extractall(extracted_dir)

        codebase_resolved = resolve_codebase_path(str(extracted_dir))

        add_job_log(job_id, f"Building AST code graph for {codebase_resolved.name}...")
        graph_json_path = job_dir / "graph.json"
        run_pure_python_extractor(codebase_resolved, graph_json_path, include_extensions=incl_list)

        add_job_log(job_id, "Persisting AST code nodes and edges into SQLite...")
        stats = gl.load_graph(graph_json_path, db_path)
        update_job_info(job_id, {"stats": stats, "progress_pct": 15})
        add_job_log(job_id, f"✅ Graph loaded: {stats.get('nodes', 0)} nodes, {stats.get('edges', 0)} edges.")

        # ── STAGE 1 (A): Architecture Snapshot ──
        update_job_info(job_id, {"current_stage": "Stage 1: Architecture Snapshot", "progress_pct": 20})
        add_job_log(job_id, "Running Stage 1: Architecture Snapshot (Prompt A)...")
        arch = stages.run_stage_a(db_path, codebase_resolved, config, lambda msg: add_job_log(job_id, msg))
        update_job_info(job_id, {"architecture": arch, "progress_pct": 25})
        add_job_log(job_id, f"✅ Stage 1 complete — {len(arch.get('modules', []))} modules identified.")

        # ── STAGE 2 (B): Leaf Node Summarization ──
        update_job_info(job_id, {"current_stage": "Stage 2: Code Summarization", "progress_pct": 30})
        add_job_log(job_id, "Running Stage 2: Code Summarization (Prompt B)...")

        def stage_b_cb(done, total):
            pct = 30 + int((done / total) * 25) if total > 0 else 30
            update_job_info(job_id, {"progress_pct": pct})

        stages.run_stage_b(db_path, codebase_resolved, config, lambda msg: add_job_log(job_id, msg), stage_b_cb)
        update_job_info(job_id, {"progress_pct": 55})
        add_job_log(job_id, "✅ Stage 2 complete.")

        # ── STAGE 3 (C): Subsystem Module Rollup ──
        update_job_info(job_id, {"current_stage": "Stage 3: Subsystem Module Rollup", "progress_pct": 60})
        add_job_log(job_id, "Running Stage 3: Subsystem Module Rollups (Prompt C)...")

        def stage_c_cb(done, total):
            pct = 60 + int((done / total) * 15) if total > 0 else 60
            update_job_info(job_id, {"progress_pct": pct})

        stages.run_stage_c(db_path, config, lambda msg: add_job_log(job_id, msg), stage_c_cb)
        update_job_info(job_id, {"progress_pct": 75})
        add_job_log(job_id, "✅ Stage 3 complete.")

        # ── STAGE 4 (D): Requirement Extraction & Auto-Freeze ──
        update_job_info(job_id, {"current_stage": "Stage 4: Requirements Extraction & Auto-Freeze", "progress_pct": 78})
        add_job_log(job_id, "Running Stage 4: Extracting Canonical Requirements (Prompt D)...")
        reqs = stages.run_stage_d(arch, db_path, config, lambda msg: add_job_log(job_id, msg))

        with open(canonical_path, "w", encoding="utf-8") as f:
            json.dump(reqs, f, indent=2)

        update_job_info(job_id, {"canonical_requirements": reqs, "progress_pct": 80})
        add_job_log(job_id, f"✅ Stage 4 complete — Canonical requirements frozen.")

        # ── STAGE 5 (E/F): Sequential Section Generation (Sections 1–10) ──
        update_job_info(job_id, {"current_stage": "Stage 5: Writing SRS Sections (Context-Aware)", "progress_pct": 82})
        srs_sections = {}
        verification_reports = {}

        sections_to_gen = [(num, title) for num, title in stages.SRS_SECTIONS if num != 11]
        n_sec = len(sections_to_gen)

        for idx, (sec_num, sec_title) in enumerate(sections_to_gen):
            add_job_log(job_id, f"▶ Writing Section {sec_num}: {sec_title}...")
            
            # Accumulate previous section context
            prev_texts = []
            for p_num in range(1, sec_num):
                p_md = srs_sections.get(f"{p_num}_sec", "")
                if p_md.strip():
                    truncated = p_md[:3000] + "\n...(truncated)..." if len(p_md) > 3000 else p_md
                    prev_texts.append(f"--- START SECTION {p_num} ---\n{truncated}\n--- END SECTION {p_num} ---")

            prev_ctx = "\n\n".join(prev_texts) if prev_texts else ""

            try:
                md = stages.run_stage_e(reqs, sec_num, sec_title, config, lambda msg: add_job_log(job_id, msg), previous_sections_context=prev_ctx)
                final_md, report = stages.run_stage_f(reqs, md, sec_num, sec_title, config, lambda msg: add_job_log(job_id, msg), previous_sections_context=prev_ctx)
                srs_sections[f"{sec_num}_sec"] = final_md
                verification_reports[sec_num] = report
            except Exception as exc:
                add_job_log(job_id, f"⚠ Section {sec_num} failed: {exc}")
                srs_sections[f"{sec_num}_sec"] = f"## {sec_num}. {sec_title}\n\n[Generation failed: {exc}]"
                verification_reports[sec_num] = {"status": "FAIL", "error": str(exc)}

            pct = 82 + int(((idx + 1) / n_sec) * 13)
            update_job_info(job_id, {"srs_sections": srs_sections, "verification_reports": verification_reports, "progress_pct": pct})

        # ── STEP 6: Section 11 & Full SRS Assembly ──
        update_job_info(job_id, {"current_stage": "Assembling Final SRS Document", "progress_pct": 96})
        add_job_log(job_id, "Auto-generating Section 11 Traceability Matrix and assembling final SRS document...")

        matrix_md = assembler._build_traceability_matrix(reqs)
        srs_sections["11_sec"] = matrix_md
        verification_reports[11] = {"status": "PASS", "info": "Auto-generated from frozen requirements"}

        sections_md = {num: srs_sections[f"{num}_sec"] for num, _ in stages.SRS_SECTIONS if f"{num}_sec" in srs_sections}
        full_doc = assembler.assemble_srs(sections_md, reqs, project_name)

        # Save document to disk
        doc_path = job_dir / f"SRS_Document_{project_name}.md"
        doc_path.write_text(full_doc, encoding="utf-8")

        audit_path = job_dir / f"SRS_Verification_Report_{project_name}.md"
        audit_report = assembler.generate_verification_report(verification_reports)
        audit_path.write_text(audit_report, encoding="utf-8")

        update_job_info(job_id, {
            "status": "COMPLETED",
            "current_stage": "Completed",
            "progress_pct": 100,
            "srs_sections": srs_sections,
            "verification_reports": verification_reports,
            "full_srs_doc": full_doc,
        })
        add_job_log(job_id, "🎉 Job completed successfully! SRS Document ready for viewing and export.")

    except Exception as e:
        err_msg = f"{e}\n{traceback.format_exc()}"
        add_job_log(job_id, f"❌ Pipeline failed: {e}")
        update_job_info(job_id, {
            "status": "FAILED",
            "current_stage": "Failed",
            "error": err_msg,
        })
