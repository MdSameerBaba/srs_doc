# tab_generate.py — Tab 2: Generate Sections

import streamlit as st
import json
import os
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pipeline import stages
from pipeline import assembler

def add_log(message: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    if "logs" not in st.session_state:
        st.session_state.logs = []
    st.session_state.logs.append(f"[{timestamp}] {message}")

def render_generate_tab(client):
    if not st.session_state.project_files:
        st.warning("⚠️ Please upload your project archive first in the **Upload Project** tab.")
        return

    output_dir = Path("srs_output")
    db_path = output_dir / "srs_graph.db"
    canonical_path = output_dir / "canonical.json"

    # Configuration Dictionary
    config = {
        "heavy_model": st.session_state.current_model,
        "fast_model": st.session_state.get("fast_model", "gemma3n:e4b"),
        "ollama_url": st.session_state.ollama_host,
        "concurrency": st.session_state.get("concurrency", 3),
    }

    # Initialize session states if not present
    if "phase_1_complete" not in st.session_state:
        st.session_state.phase_1_complete = canonical_path.exists()
    if "requirements_frozen" not in st.session_state:
        # If the file exists and is read-only, it's frozen
        st.session_state.requirements_frozen = False
        if canonical_path.exists():
            # On Linux/Windows, check if read-only (we can check file permissions)
            st.session_state.requirements_frozen = not os.access(canonical_path, os.W_OK)

    # ─────────────────────────────────────────────────────────────
    # STEP 1: REQUIREMENT EXTRACTION & FREEZE GATE (PHASE 1)
    # ─────────────────────────────────────────────────────────────
    if not st.session_state.phase_1_complete:
        st.markdown("### 🔒 Step 1: Extract & Synthesize Codebase Requirements")
        st.info(
            "Before generating the final SRS document, the AI must first analyze the SQLite call-graph, "
            "summarize code nodes, and extract a frozen set of canonical requirements. "
            "This guarantees 100% traceability and prevents hallucinations."
        )
        
        # Concurrency settings in main view
        st.markdown("#### Concurrency & Engine Override")
        c_col1, c_col2 = st.columns(2)
        with c_col1:
            st.session_state.concurrency = st.slider(
                "Concurrent Workers (Stage B)",
                min_value=1, max_value=10,
                value=st.session_state.get("concurrency", 3),
                key="tab_concurrency"
            )
        with c_col2:
            st.session_state.current_model = st.text_input(
                "Heavy Model Override",
                value=st.session_state.current_model,
                key="tab_heavy_model_override"
            )

        extract_btn = st.button("🔍 Run Requirements Extraction (Stages 1–4)", type="primary", use_container_width=True)

        if extract_btn:
            st.session_state.logs = []
            
            # Re-verify database exists
            if not db_path.exists():
                st.error("SQLite database not found. Please re-upload your project in Tab 1.")
                return

            status_placeholder = st.empty()
            progress_placeholder = st.empty()
            log_placeholder = st.empty()

            with st.spinner("Analyzing codebase and extracting requirements..."):
                # ── STAGE 1: Architecture Snapshot ──
                st.session_state.stage_status[1] = "running"
                add_log("Stage 1: Building Architecture Snapshot (Prompt A)...")
                log_placeholder.code("\n".join(st.session_state.logs[-10:]))
                try:
                    codebase_dir = Path(st.session_state.codebase_path) if st.session_state.get("codebase_path") else Path("srs_output/extracted_codebase")
                    arch = stages.run_stage_a(db_path, codebase_dir, config, add_log)
                    st.session_state.architecture = arch
                    st.session_state.stage_status[1] = "complete"
                except Exception as e:
                    st.session_state.stage_status[1] = "failed"
                    st.error(f"Stage 1 failed: {e}")
                    return

                # ── STAGE 2: Leaf Node Summarization ──
                st.session_state.stage_status[2] = "running"
                add_log("Stage 2: Running Leaf Node Summarization (Prompt B)...")
                log_placeholder.code("\n".join(st.session_state.logs[-10:]))
                try:
                    def stage_b_progress(completed, total):
                        pct = completed / total if total > 0 else 0
                        progress_placeholder.progress(pct, text=f"Summarized {completed}/{total} leaf nodes...")
                    codebase_dir = Path(st.session_state.codebase_path) if st.session_state.get("codebase_path") else Path("srs_output/extracted_codebase")
                    stages.run_stage_b(db_path, codebase_dir, config, add_log, stage_b_progress)
                    progress_placeholder.empty()
                    st.session_state.stage_status[2] = "complete"
                except Exception as e:
                    st.session_state.stage_status[2] = "failed"
                    st.error(f"Stage 2 failed: {e}")
                    return

                # ── STAGE 3: Module Rollup ──
                st.session_state.stage_status[3] = "running"
                add_log("Stage 3: Running Module Rollups (Prompt C)...")
                log_placeholder.code("\n".join(st.session_state.logs[-10:]))
                try:
                    def stage_c_progress(completed, total):
                        pct = completed / total if total > 0 else 0
                        progress_placeholder.progress(pct, text=f"Rolled up {completed}/{total} modules...")
                    stages.run_stage_c(db_path, config, add_log, stage_c_progress)
                    progress_placeholder.empty()
                    st.session_state.stage_status[3] = "complete"
                except Exception as e:
                    st.session_state.stage_status[3] = "failed"
                    st.error(f"Stage 3 failed: {e}")
                    return

                # ── STAGE 4: Requirement Extraction (Freeze Point) ──
                st.session_state.stage_status[4] = "running"
                add_log("Stage 4: Extracting canonical requirements (Prompt D)...")
                log_placeholder.code("\n".join(st.session_state.logs[-10:]))
                try:
                    reqs = stages.run_stage_d(st.session_state.architecture, db_path, config, add_log)
                    st.session_state.canonical_requirements = reqs
                    st.session_state.stage_status[4] = "complete"
                    
                    # Write to disk initially
                    if canonical_path.exists():
                        try:
                            os.chmod(canonical_path, 0o666)
                        except Exception:
                            pass
                    with open(canonical_path, "w", encoding="utf-8") as f:
                        json.dump(reqs, f, indent=2)
                        
                    st.session_state.phase_1_complete = True
                    add_log("✅ Phase 1 complete. Locked in requirements.")
                    st.rerun()
                except Exception as e:
                    st.session_state.stage_status[4] = "failed"
                    st.error(f"Stage 4 failed: {e}")
                    return
        return

    # ─────────────────────────────────────────────────────────────
    # STEP 2: REQUIREMENT FREEZE GATE (EDITABLE INTERFACE)
    # ─────────────────────────────────────────────────────────────
    if not st.session_state.requirements_frozen:
        st.markdown("### 🔒 Freeze Gate: Verify & Lock Canonical Requirements")
        st.warning(
            "Requirements have been successfully extracted! Review the JSON specification below. "
            "You can modify requirement titles, descriptions, and categories. Once you click "
            "'Approve & Freeze', the requirements file will be locked as read-only to prevent "
            "downstream modifications."
        )

        try:
            with open(canonical_path, "r", encoding="utf-8") as f:
                reqs_json_text = f.read()
        except Exception:
            reqs_json_text = json.dumps(st.session_state.canonical_requirements, indent=2)

        edited_json = st.text_area("Canonical Requirements JSON Specification", value=reqs_json_text, height=400)

        col_f1, col_f2 = st.columns([1, 3])
        with col_f1:
            approve_btn = st.button("🔒 Approve & Freeze", type="primary", use_container_width=True)
        with col_f2:
            if st.button("🔄 Regenerate Requirements"):
                st.session_state.phase_1_complete = False
                st.rerun()

        if approve_btn:
            try:
                parsed_json = json.loads(edited_json)
                if canonical_path.exists():
                    try:
                        os.chmod(canonical_path, 0o666)
                    except Exception:
                        pass
                with open(canonical_path, "w", encoding="utf-8") as f:
                    json.dump(parsed_json, f, indent=2)
                
                # Lock the file as read-only
                try:
                    os.chmod(canonical_path, 0o444)
                except Exception:
                    pass

                st.session_state.canonical_requirements = parsed_json
                st.session_state.requirements_frozen = True

                # Auto-generate Section 11 from frozen requirements
                matrix_md = assembler._build_traceability_matrix(parsed_json)
                st.session_state.srs_sections["11_sec"] = matrix_md
                if "verification_reports" not in st.session_state:
                    st.session_state.verification_reports = {}
                st.session_state.verification_reports[11] = {"status": "PASS", "info": "Auto-generated from frozen requirements"}

                st.success("🔒 Requirements successfully frozen! Proceeding to document writing.")
                st.rerun()
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON: {e}. Please correct formatting errors before freezing.")
        return

    # ─────────────────────────────────────────────────────────────
    # STEP 3: CONCURRENT SECTION WRITING & AUDITING (PHASE 2)
    # ─────────────────────────────────────────────────────────────
    st.markdown("### ⚡ Generate SRS Sections")
    st.markdown("🔒 **Requirements Status**: `FROZEN` (Ready for document writing)")

    col_all1, col_all2 = st.columns([2, 1])
    with col_all1:
        gen_all = st.button(
            "🚀 Generate ALL Sections (Concurrent Thread Pool)",
            use_container_width=True,
            type="primary",
            key="gen_all_btn"
        )
    with col_all2:
        if st.button("🔓 Unlock & Reset Requirements", use_container_width=True, key="unlock_all"):
            if canonical_path.exists():
                try:
                    os.chmod(canonical_path, 0o666)
                    canonical_path.unlink()
                except Exception:
                    pass
            st.session_state.phase_1_complete = False
            st.session_state.requirements_frozen = False
            st.session_state.srs_sections = {}
            st.session_state.verification_reports = {}
            st.rerun()

    st.markdown("---")

    # ── Handle concurrent full document generation ──
    if gen_all:
        status_ph = st.empty()
        progress_ph = st.empty()
        log_ph = st.empty()
        st.session_state.logs = []

        add_log("🚀 Launching concurrent section generation and audit threads...")
        log_ph.code("\n".join(st.session_state.logs[-10:]))

        with open(canonical_path, "r", encoding="utf-8") as f:
            canonical = json.load(f)

        sections_md = {}
        reports = {}
        total_sections = len(stages.SRS_SECTIONS)
        completed = 0

        # Thread-safe log collection list (GIL ensures list.append is thread-safe)
        log_queue = []
        def thread_safe_log(msg):
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_queue.append(f"[{timestamp}] {msg}")

        def process_section(sec_num, sec_title):
            thread_safe_log(f"Starting Thread: Section {sec_num} ({sec_title})")
            # Stage E: Write
            md = stages.run_stage_e(canonical, sec_num, sec_title, config, thread_safe_log)
            # Stage F: Audit
            final_md, report = stages.run_stage_f(canonical, md, sec_num, sec_title, config, thread_safe_log)
            return sec_num, final_md, report

        # Exclude Section 11 from concurrent LLM generation (auto-generated in Python)
        srs_sections_to_gen = [(num, title) for num, title in stages.SRS_SECTIONS if num != 11]
        n_to_gen = len(srs_sections_to_gen)
        workers = min(config["concurrency"], n_to_gen)

        import time
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures_map = {executor.submit(process_section, num, title): (num, title) for num, title in srs_sections_to_gen}
            
            while any(not f.done() for f in futures_map):
                # Flush the thread-safe logs into session state in the main thread
                while log_queue:
                    st.session_state.logs.append(log_queue.pop(0))
                if st.session_state.logs:
                    log_ph.code("\n".join(st.session_state.logs[-12:]))
                
                done_count = sum(1 for f in futures_map if f.done())
                pct = done_count / n_to_gen  # denominator is sections actually submitted
                progress_ph.progress(pct, text=f"Writing and auditing sections ({done_count}/{n_to_gen} done)...")
                time.sleep(0.5)

            # Final check and process results
            while log_queue:
                st.session_state.logs.append(log_queue.pop(0))
            if st.session_state.logs:
                log_ph.code("\n".join(st.session_state.logs[-12:]))

            for future, (num, title) in futures_map.items():
                try:
                    sec_num, final_md, report = future.result()
                    sections_md[sec_num] = final_md
                    reports[sec_num] = report
                    add_log(f"✅ Section {num} completed successfully ({report.get('status', 'UNKNOWN')}).")
                except Exception as e:
                    add_log(f"❌ Section {num} failed: {e}")
                    sections_md[num] = f"## {num}. {title}\n\n[Failed to generate due to error: {e}]"
                    reports[num] = {"status": "FAIL", "error": str(e)}

            # Force append the mathematically exact auto-generated Section 11 matrix
            sections_md[11] = assembler._build_traceability_matrix(canonical)
            reports[11] = {"status": "PASS", "info": "Auto-generated from frozen requirements"}

        progress_ph.empty()
        
        # Save results to session state
        st.session_state.srs_sections = {f"{num}_sec": md for num, md in sections_md.items()}
        st.session_state.verification_reports = reports

        # Assemble full documents
        proj_name = Path(st.session_state.codebase_path).name
        if (proj_name == "extracted_codebase" or not proj_name) and st.session_state.get("archive_name"):
            proj_name = st.session_state.archive_name
        st.session_state.full_srs_doc = assembler.assemble_srs(sections_md, canonical, proj_name)
        
        st.success("🎉 All sections generated and audited successfully! Go to **Preview & Export** tab.")
        st.rerun()

    # ── Per-section cards ──
    # Load canonical for individual runs — guard against missing file
    if not canonical_path.exists():
        st.error("canonical.json not found. Please re-run requirements extraction.")
        return
    with open(canonical_path, "r", encoding="utf-8") as f:
        canonical = json.load(f)

    for sec_num, sec_title in stages.SRS_SECTIONS:
        sec_key = f"{sec_num}_sec"
        is_done = sec_key in st.session_state.srs_sections and st.session_state.srs_sections[sec_key].strip()
        card_cls = "section-card section-done" if is_done else "section-card section-pending"
        badge = '<span class="status-badge-done">✅ Generated</span>' if is_done else '<span class="status-badge-pending">⬜ Pending</span>'

        st.markdown(f'<div class="{card_cls}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            st.markdown(f"**{sec_num}. {sec_title}** &nbsp; {badge}", unsafe_allow_html=True)
        with c2:
            if st.button(
                "🔄 Regenerate" if is_done else "▶️ Generate",
                use_container_width=True,
                key=f"gen_{sec_num}",
            ):
                st.session_state[f"generating_{sec_num}"] = True
        with c3:
            if is_done:
                if st.button("👁️ View", use_container_width=True, key=f"view_{sec_num}"):
                    st.session_state[f"expand_{sec_num}"] = not st.session_state.get(f"expand_{sec_num}", False)

        st.markdown("</div>", unsafe_allow_html=True)

        # Handle individual section generation
        if st.session_state.get(f"generating_{sec_num}"):
            st.session_state[f"generating_{sec_num}"] = False
            with st.container():
                st.markdown(f"#### ⚙️ Generating Section {sec_num}: {sec_title}…")
                try:
                    if sec_num == 11:
                        # Generate in pure Python instantly
                        final_md = assembler._build_traceability_matrix(canonical)
                        report = {"status": "PASS", "info": "Auto-generated from frozen requirements"}
                    else:
                        # Stage E: Write
                        md = stages.run_stage_e(canonical, sec_num, sec_title, config, add_log)
                        # Stage F: Audit
                        final_md, report = stages.run_stage_f(canonical, md, sec_num, sec_title, config, add_log)
                    
                    st.session_state.srs_sections[sec_key] = final_md
                    if "verification_reports" not in st.session_state:
                        st.session_state.verification_reports = {}
                    st.session_state.verification_reports[sec_num] = report
                    st.success(f"✅ Section {sec_num} written and verified ({report.get('status', 'UNKNOWN')})!")
                except Exception as e:
                    st.error(f"❌ Failed to generate Section {sec_num}: {e}")
                st.rerun()

        # Handle inline preview expander
        if st.session_state.get(f"expand_{sec_num}") and is_done:
            with st.expander(f"📖 Section {sec_num} — Preview", expanded=True):
                st.markdown(st.session_state.srs_sections[sec_key])
                col_dl, col_copy = st.columns(2)
                with col_dl:
                    assembler_safe_title = sec_title.replace(" ", "_").replace(".", "")
                    st.download_button(
                        label="⬇️ Download Section",
                        data=st.session_state.srs_sections[sec_key],
                        file_name=f"SRS_{assembler_safe_title}.md",
                        mime="text/markdown",
                        key=f"dl_{sec_num}"
                    )
                with col_copy:
                    if st.button("📋 Show Raw Text", key=f"raw_{sec_num}"):
                        st.code(st.session_state.srs_sections[sec_key])
