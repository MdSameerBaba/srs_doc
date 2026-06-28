# tab_preview.py — Tab 3: Preview & Export

import streamlit as st
import json
from pathlib import Path
from pipeline import stages
from pipeline import assembler

def render_preview_tab():
    output_dir = Path("srs_output")
    canonical_path = output_dir / "canonical.json"
    
    # Verify canonical requirements exist
    if not canonical_path.exists():
        st.warning("⚠️ Requirements have not been frozen yet. Please extract and freeze them in the **Generate Sections** tab.")
        return
        
    with open(canonical_path, "r", encoding="utf-8") as f:
        canonical = json.load(f)

    # Convert session state srs_sections keys (e.g. '1_sec') to integers for assembler
    sections_by_num = {}
    for k, v in st.session_state.srs_sections.items():
        if k.endswith("_sec") and v.strip():
            try:
                num = int(k.split("_")[0])
                sections_by_num[num] = v
            except ValueError:
                pass

    done_count = len(sections_by_num)
    total_expected = len(stages.SRS_SECTIONS)

    if done_count == 0:
        st.warning("⚠️ No sections generated yet. Go to the **Generate Sections** tab to write your SRS.")
        return

    st.markdown(f"### 📄 SRS Document Preview — {done_count}/{total_expected} Sections Written")

    # Assemble full document
    project_name = "Unknown Project"
    if st.session_state.get("codebase_path"):
        p_name = Path(st.session_state.codebase_path).name
        if p_name and p_name != "extracted_codebase":
            project_name = p_name
    if project_name == "Unknown Project" and st.session_state.get("archive_name"):
        project_name = st.session_state.archive_name
    full_doc = assembler.assemble_srs(sections_by_num, canonical, project_name)
    st.session_state.full_srs_doc = full_doc

    # Assembly stats
    col_dl1, col_dl2, col_dl3 = st.columns(3)
    with col_dl1:
        st.metric("Estimated Pages", f"~{max(1, len(full_doc) // 3000)} pages")
    with col_dl2:
        st.metric("Total Characters", f"{len(full_doc):,}")
    with col_dl3:
        st.metric("Requirement Coverage", f"{len(canonical.get('functional_requirements', []))} FRs mapped")

    st.markdown("---")

    # Exports Row
    st.markdown("#### 📥 Exports")
    exp_cols = st.columns(3)
    with exp_cols[0]:
        st.download_button(
            label="📄 Download Full SRS Document (.md)",
            data=full_doc,
            file_name=f"SRS_Document_{project_name}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with exp_cols[1]:
        # Generate and download audit report
        reports = st.session_state.get("verification_reports", {})
        audit_report = assembler.generate_verification_report(reports)
        st.download_button(
            label="🛡️ Download Verification Audit Report (.md)",
            data=audit_report,
            file_name=f"SRS_Verification_Report_{project_name}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with exp_cols[2]:
        # Download canonical JSON
        with open(canonical_path, "r", encoding="utf-8") as f:
            canonical_json_text = f.read()
        st.download_button(
            label="🔒 Download Canonical Requirements (.json)",
            data=canonical_json_text,
            file_name=f"canonical_requirements_{project_name}.json",
            mime="application/json",
            use_container_width=True,
        )

    st.markdown("---")

    # Split into preview and audit tabs
    sub_tab_preview, sub_tab_audit = st.tabs(["📖 Full Document Viewer", "🛡️ Verification Audit Dashboard"])

    with sub_tab_preview:
        # Table of contents
        st.markdown("#### 📑 Table of Contents")
        for sec_num, sec_title in stages.SRS_SECTIONS:
            is_done = sec_num in sections_by_num
            status = "✅" if is_done else "⬜"
            st.markdown(f"{status} **{sec_num}. {sec_title}**")
            
        st.markdown("---")
        st.markdown("#### 📖 Document Body")
        
        # Render each section inside expanders
        for sec_num, sec_title in stages.SRS_SECTIONS:
            is_done = sec_num in sections_by_num
            if is_done:
                with st.expander(f"📝 {sec_num}. {sec_title}", expanded=False):
                    st.markdown(sections_by_num[sec_num])
                    
                    col_sec_dl, col_sec_raw = st.columns(2)
                    with col_sec_dl:
                        assembler_safe_title = sec_title.replace(" ", "_").replace(".", "")
                        st.download_button(
                            label="⬇️ Download Section",
                            data=sections_by_num[sec_num],
                            file_name=f"SRS_Section_{sec_num}_{assembler_safe_title}.md",
                            mime="text/markdown",
                            key=f"preview_dl_{sec_num}"
                        )
                    with col_sec_raw:
                        if st.button("📋 Show Raw Text", key=f"preview_raw_{sec_num}"):
                            st.code(sections_by_num[sec_num])
                            
        # If Section 11 is not yet in sections, show the auto-generated Traceability Matrix
        if 11 not in sections_by_num:
            with st.expander("📝 11. Traceability Matrix (Auto-generated from frozen requirements)", expanded=True):
                st.markdown(assembler._build_traceability_matrix(canonical))

    with sub_tab_audit:
        reports = st.session_state.get("verification_reports", {})
        if not reports:
            st.info("No verification audits compiled yet. Run generation in Tab 2 to audit sections.")
        else:
            st.markdown(assembler.generate_verification_report(reports))
