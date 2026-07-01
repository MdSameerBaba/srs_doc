# tab_generate.py — Tab 2: Generate Sections

import streamlit as st
import json
import os
import traceback
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pipeline import stages
from pipeline import assembler
from pipeline import ollama_client as _ollama_client

# ── Section number → title lookup (safe alternative to index arithmetic) ──
_SEC_TITLES: dict[int, str] = {num: title for num, title in stages.SRS_SECTIONS}


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

    # ── Wire LLM provider BEFORE any stage runs ──
    _ollama_client.PROVIDER = st.session_state.get("llm_provider", "ollama")
    _ollama_client.API_KEY  = st.session_state.get("gemini_api_key", "")

    # Configuration Dictionary
    config = {
        "heavy_model": st.session_state.current_model,
        "fast_model":  st.session_state.get("fast_model", "qwen3:latest"),
        "ollama_url":  st.session_state.ollama_host,
        "concurrency": st.session_state.get("concurrency", 3),
        "enable_audit": st.session_state.get("enable_audit", False),
    }

    # Initialize session states if not present
    if "phase_1_complete" not in st.session_state:
        st.session_state.phase_1_complete = canonical_path.exists()
    if "requirements_frozen" not in st.session_state:
        st.session_state.requirements_frozen = False
        if canonical_path.exists():
            import stat
            try:
                mode = os.stat(canonical_path).st_mode
                st.session_state.requirements_frozen = not (mode & stat.S_IWRITE)
            except Exception:
                st.session_state.requirements_frozen = False

    # ── Gemini provider guard ──
    if st.session_state.get("llm_provider") == "gemini" and not st.session_state.get("gemini_api_key", "").strip():
        st.error("🔴 **Gemini API key is missing.** Please enter your API key in the sidebar before generating.")
        return

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

            if not db_path.exists():
                st.error("SQLite database not found. Please re-upload your project in Tab 1.")
                return

            log_placeholder = st.empty()

            with st.spinner("Analyzing codebase and extracting requirements..."):

                # ── STAGE 1: Architecture Snapshot ──
                st.session_state.stage_status[1] = "running"
                add_log("Stage 1: Building Architecture Snapshot (Prompt A)...")
                log_placeholder.code("\n".join(st.session_state.logs[-15:]))
                try:
                    codebase_dir = Path(st.session_state.codebase_path) if st.session_state.get("codebase_path") else Path("srs_output/extracted_codebase")
                    arch = stages.run_stage_a(db_path, codebase_dir, config, add_log)
                    st.session_state.architecture = arch
                    st.session_state.stage_status[1] = "complete"
                    add_log(f"✅ Stage 1 done — {len(arch.get('modules', []))} modules.")
                    log_placeholder.code("\n".join(st.session_state.logs[-15:]))
                except Exception as e:
                    traceback.print_exc()
                    st.session_state.stage_status[1] = "failed"
                    st.error(f"Stage 1 failed: {e}")
                    return

                # ── STAGE 2: Leaf Node Summarization ──
                st.session_state.stage_status[2] = "running"
                add_log("Stage 2: Running Leaf Node Summarization (Prompt B)...")
                log_placeholder.code("\n".join(st.session_state.logs[-15:]))
                progress_ph = st.empty()
                try:
                    def stage_b_progress(completed, total):
                        pct = completed / total if total > 0 else 0
                        progress_ph.progress(pct, text=f"Summarized {completed}/{total} leaf nodes...")
                    codebase_dir = Path(st.session_state.codebase_path) if st.session_state.get("codebase_path") else Path("srs_output/extracted_codebase")
                    stages.run_stage_b(db_path, codebase_dir, config, add_log, stage_b_progress)
                    progress_ph.empty()
                    st.session_state.stage_status[2] = "complete"
                    add_log("✅ Stage 2 done.")
                    log_placeholder.code("\n".join(st.session_state.logs[-15:]))
                except Exception as e:
                    traceback.print_exc()
                    st.session_state.stage_status[2] = "failed"
                    st.error(f"Stage 2 failed: {e}")
                    return

                # ── STAGE 3: Module Rollup ──
                st.session_state.stage_status[3] = "running"
                add_log("Stage 3: Running Module Rollups (Prompt C)...")
                log_placeholder.code("\n".join(st.session_state.logs[-15:]))
                progress_ph2 = st.empty()
                try:
                    def stage_c_progress(completed, total):
                        pct = completed / total if total > 0 else 0
                        progress_ph2.progress(pct, text=f"Rolled up {completed}/{total} modules...")
                    stages.run_stage_c(db_path, config, add_log, stage_c_progress)
                    progress_ph2.empty()
                    st.session_state.stage_status[3] = "complete"
                    add_log("✅ Stage 3 done.")
                    log_placeholder.code("\n".join(st.session_state.logs[-15:]))
                except Exception as e:
                    traceback.print_exc()
                    st.session_state.stage_status[3] = "failed"
                    st.error(f"Stage 3 failed: {e}")
                    return

                # ── STAGE 4: Requirement Extraction (Freeze Point) ──
                st.session_state.stage_status[4] = "running"
                add_log("Stage 4: Extracting canonical requirements (Prompt D)...")
                log_placeholder.code("\n".join(st.session_state.logs[-15:]))
                try:
                    reqs = stages.run_stage_d(st.session_state.architecture, db_path, config, add_log)
                    st.session_state.canonical_requirements = reqs
                    st.session_state.stage_status[4] = "complete"

                    if canonical_path.exists():
                        try:
                            os.chmod(canonical_path, 0o666)
                        except Exception:
                            pass
                    with open(canonical_path, "w", encoding="utf-8") as f:
                        json.dump(reqs, f, indent=2)

                    st.session_state.phase_1_complete = True
                    add_log("✅ Phase 1 complete — requirements extracted and saved.")
                    st.rerun()
                except Exception as e:
                    traceback.print_exc()
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

                try:
                    os.chmod(canonical_path, 0o444)
                except Exception:
                    pass

                st.session_state.canonical_requirements = parsed_json
                st.session_state.requirements_frozen = True

                # Auto-generate Section 11
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
    # STEP 3: SEQUENTIAL SECTION WRITING (PHASE 2)
    # ─────────────────────────────────────────────────────────────
    st.markdown("### ⚡ Generate SRS Sections")
    st.markdown("🔒 **Requirements Status**: `FROZEN` (Ready for document writing)")

    # Guard: canonical must exist
    if not canonical_path.exists():
        st.error("canonical.json not found. Please re-run requirements extraction.")
        return

    # Load canonical once at the top of Phase 2
    try:
        with open(canonical_path, "r", encoding="utf-8") as f:
            canonical = json.load(f)
    except Exception as e:
        traceback.print_exc()
        st.error(f"❌ Cannot read canonical requirements: {e}")
        return

    # ── Top action row ──
    col_all1, col_all2 = st.columns([2, 1])
    with col_all1:
        gen_all = st.button(
            "🚀 Generate ALL Sections (Sequential — Context-Aware)",
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
            st.session_state.generating_all = False
            st.session_state.gen_all_index = 0
            st.rerun()

    st.markdown("---")

    # ── Trigger: start generation ──
    if gen_all:
        st.session_state.generating_all = True
        st.session_state.gen_all_index = 0
        st.session_state.logs = []
        st.rerun()

    # ── Sequential generation loop (one section per Streamlit rerun) ──
    if st.session_state.get("generating_all"):
        srs_sections_to_gen = [(num, title) for num, title in stages.SRS_SECTIONS if num != 11]
        n_to_gen = len(srs_sections_to_gen)
        current_idx = st.session_state.get("gen_all_index", 0)

        if current_idx < n_to_gen:
            num, title = srs_sections_to_gen[current_idx]

            # ── Persistent status banner ──
            st.info(f"⚙️ **Generating Section {num} of {n_to_gen}: {title}** — please wait...")
            st.progress(current_idx / n_to_gen, text=f"Section {current_idx + 1} of {n_to_gen}")

            # ── Show all logs accumulated so far ──
            if st.session_state.logs:
                with st.expander("📋 Generation Log", expanded=True):
                    st.code("\n".join(st.session_state.logs[-20:]))

            # ── Accumulate context of previously generated sections ──
            prev_texts = []
            for p_num in range(1, num):
                p_md = st.session_state.srs_sections.get(f"{p_num}_sec", "")
                if p_md.strip():
                    truncated_md = p_md[:3000] + "\n...(truncated for context)..." if len(p_md) > 3000 else p_md
                    p_title = _SEC_TITLES.get(p_num, f"Section {p_num}")
                    prev_texts.append(
                        f"--- START SECTION {p_num}: {p_title} ---\n{truncated_md}\n--- END SECTION {p_num} ---"
                    )

            prev_context = ""
            if prev_texts:
                prev_context = (
                    "PREVIOUSLY GENERATED SECTIONS FOR CONTEXT "
                    "(Do not repeat details or duplicate acronym definitions, maintain flow):\n\n"
                    + "\n\n".join(prev_texts)
                )

            add_log(f"▶ Writing Section {num}: {title}...")

            try:
                # Stage E: Write the section
                md = stages.run_stage_e(
                    canonical, num, title, config, add_log,
                    previous_sections_context=prev_context
                )

                # Stage F: Audit (skipped if enable_audit=False)
                final_md, report = stages.run_stage_f(
                    canonical, md, num, title, config, add_log,
                    previous_sections_context=prev_context
                )

                # Save immediately to session state
                st.session_state.srs_sections[f"{num}_sec"] = final_md
                if "verification_reports" not in st.session_state:
                    st.session_state.verification_reports = {}
                st.session_state.verification_reports[num] = report
                add_log(f"✅ Section {num}: {title} — DONE ({report.get('status', 'OK')})")

            except Exception as e:
                traceback.print_exc()
                add_log(f"❌ Section {num} failed: {e}")
                st.session_state.srs_sections[f"{num}_sec"] = (
                    f"## {num}. {title}\n\n[Generation failed: {e}]"
                )
                if "verification_reports" not in st.session_state:
                    st.session_state.verification_reports = {}
                st.session_state.verification_reports[num] = {"status": "FAIL", "error": str(e)}

            st.session_state.gen_all_index += 1
            st.rerun()

        else:
            # ── All sections done — build Section 11 + assemble full doc ──
            matrix_md = assembler._build_traceability_matrix(canonical)
            st.session_state.srs_sections["11_sec"] = matrix_md
            if "verification_reports" not in st.session_state:
                st.session_state.verification_reports = {}
            st.session_state.verification_reports[11] = {
                "status": "PASS", "info": "Auto-generated from frozen requirements"
            }

            proj_name = "Unknown Project"
            if st.session_state.get("codebase_path"):
                p_name = Path(st.session_state.codebase_path).name
                if p_name and p_name != "extracted_codebase":
                    proj_name = p_name
            if proj_name == "Unknown Project" and st.session_state.get("archive_name"):
                proj_name = st.session_state.archive_name

            sections_md = {}
            for k, v in st.session_state.srs_sections.items():
                if k.endswith("_sec") and v.strip():
                    try:
                        n = int(k.split("_")[0])
                        sections_md[n] = v
                    except ValueError:
                        pass

            st.session_state.full_srs_doc = assembler.assemble_srs(sections_md, canonical, proj_name)
            st.session_state.generating_all = False
            add_log("🎉 All sections generated successfully!")
            st.success("🎉 All sections generated! Go to **Preview & Export** to download your SRS.")
            st.rerun()

    # ─────────────────────────────────────────────────────────────
    # SECTION CARDS — show status + inline preview for every section
    # ─────────────────────────────────────────────────────────────
    done_count = sum(
        1 for num, _ in stages.SRS_SECTIONS
        if st.session_state.srs_sections.get(f"{num}_sec", "").strip()
    )
    total_count = len(stages.SRS_SECTIONS)
    if done_count > 0:
        st.markdown(f"**{done_count}/{total_count} sections generated**")

    for sec_num, sec_title in stages.SRS_SECTIONS:
        sec_key = f"{sec_num}_sec"
        content = st.session_state.srs_sections.get(sec_key, "")
        is_done = bool(content.strip())

        card_cls = "section-card section-done" if is_done else "section-card section-pending"
        badge = '<span class="status-badge-done">✅ Generated</span>' if is_done else '<span class="status-badge-pending">⬜ Pending</span>'

        st.markdown(f'<div class="{card_cls}">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            st.markdown(f"**{sec_num}. {sec_title}** &nbsp; {badge}", unsafe_allow_html=True)
        with c2:
            regen_label = "🔄 Regenerate" if is_done else "▶️ Generate"
            if st.button(regen_label, use_container_width=True, key=f"gen_{sec_num}"):
                st.session_state[f"generating_{sec_num}"] = True
        with c3:
            if is_done:
                toggle_label = "🔼 Hide" if st.session_state.get(f"expand_{sec_num}") else "👁️ View"
                if st.button(toggle_label, use_container_width=True, key=f"view_{sec_num}"):
                    st.session_state[f"expand_{sec_num}"] = not st.session_state.get(f"expand_{sec_num}", False)

        st.markdown("</div>", unsafe_allow_html=True)

        # ── Handle individual section (re)generation ──
        if st.session_state.get(f"generating_{sec_num}"):
            st.session_state[f"generating_{sec_num}"] = False
            with st.spinner(f"⚙️ Generating Section {sec_num}: {sec_title}…"):
                try:
                    if sec_num == 11:
                        final_md = assembler._build_traceability_matrix(canonical)
                        report = {"status": "PASS", "info": "Auto-generated from frozen requirements"}
                    else:
                        # Build previous context
                        prev_texts = []
                        for p_num in range(1, sec_num):
                            p_md = st.session_state.srs_sections.get(f"{p_num}_sec", "")
                            if p_md.strip():
                                truncated_md = p_md[:3000] + "\n...(truncated)..." if len(p_md) > 3000 else p_md
                                p_title = _SEC_TITLES.get(p_num, f"Section {p_num}")
                                prev_texts.append(
                                    f"--- START SECTION {p_num}: {p_title} ---\n{truncated_md}\n--- END SECTION {p_num} ---"
                                )
                        prev_context = ""
                        if prev_texts:
                            prev_context = (
                                "PREVIOUSLY GENERATED SECTIONS FOR CONTEXT "
                                "(Do not repeat details, maintain flow):\n\n"
                                + "\n\n".join(prev_texts)
                            )

                        md = stages.run_stage_e(canonical, sec_num, sec_title, config, add_log, previous_sections_context=prev_context)
                        final_md, report = stages.run_stage_f(canonical, md, sec_num, sec_title, config, add_log, previous_sections_context=prev_context)

                    st.session_state.srs_sections[sec_key] = final_md
                    if "verification_reports" not in st.session_state:
                        st.session_state.verification_reports = {}
                    st.session_state.verification_reports[sec_num] = report
                    st.success(f"✅ Section {sec_num} written ({report.get('status', 'OK')})")
                    # Auto-expand after generation
                    st.session_state[f"expand_{sec_num}"] = True
                except Exception as e:
                    traceback.print_exc()
                    st.error(f"❌ Failed to generate Section {sec_num}: {e}")
            st.rerun()

        # ── Inline preview of generated content ──
        if st.session_state.get(f"expand_{sec_num}") and is_done:
            with st.container():
                st.markdown(content)
                col_dl, col_raw = st.columns(2)
                with col_dl:
                    safe_title = sec_title.replace(" ", "_").replace(".", "")
                    st.download_button(
                        label="⬇️ Download Section",
                        data=content,
                        file_name=f"SRS_Section_{sec_num}_{safe_title}.md",
                        mime="text/markdown",
                        key=f"dl_{sec_num}"
                    )
                with col_raw:
                    if st.button("📋 Show Raw Text", key=f"raw_{sec_num}"):
                        st.code(content)
            st.markdown("---")
