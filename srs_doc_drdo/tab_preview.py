# tab_preview.py — Tab 3: Preview & Export SRS Document

import streamlit as st
import json
from pathlib import Path
from pipeline import stages
from pipeline import assembler
from pipeline import job_manager


def render_preview_tab():
    st.markdown("### 📄 Preview & Export Generated SRS Documents")

    jobs = job_manager.list_all_jobs()
    completed_jobs = [j for j in jobs if j.get("status") == "COMPLETED"]

    if not completed_jobs:
        st.warning("⚠️ No completed SRS document jobs available yet. Submit and run a project in the **Upload Project** tab.")
        return

    # Select box to pick completed job
    job_options = {j["job_id"]: f"{j['archive_name']} — ({j['created_at']})" for j in completed_jobs}
    
    # Pre-select if selected via Dashboard button or active job
    default_id = st.session_state.get("selected_job_for_preview") or completed_jobs[0]["job_id"]
    if default_id not in job_options:
        default_id = completed_jobs[0]["job_id"]

    selected_jid = st.selectbox(
        "Select Completed SRS Document Job",
        options=list(job_options.keys()),
        format_func=lambda jid: job_options[jid],
        index=list(job_options.keys()).index(default_id),
        key="select_preview_job_dropdown"
    )

    job = job_manager.get_job_info(selected_jid)
    if not job:
        st.error("Cannot load selected job info.")
        return

    project_name = job.get("clean_project_name", "Project")
    full_doc = job.get("full_srs_doc", "")
    canonical = job.get("canonical_requirements", {})
    srs_sections = job.get("srs_sections", {})
    verification_reports = job.get("verification_reports", {})
    stats = job.get("stats", {})

    job_dir = job_manager.BASE_JOBS_DIR / selected_jid
    canonical_path = job_dir / "canonical.json"

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
    exp_cols = st.columns(4)
    with exp_cols[0]:
        st.download_button(
            label="📄 Download SRS (.md)",
            data=full_doc,
            file_name=f"SRS_Document_{project_name}.md",
            mime="text/markdown",
            use_container_width=True,
            key=f"dl_full_srs_{selected_jid}"
        )
    with exp_cols[1]:
        docx_path = job_dir / f"SRS_Document_{project_name}.docx"
        if docx_path.exists():
            try:
                docx_bytes = docx_path.read_bytes()
            except Exception:
                docx_bytes = assembler.create_docx_bytes(full_doc, project_name)
        else:
            docx_bytes = assembler.create_docx_bytes(full_doc, project_name)

        st.download_button(
            label="📝 Download SRS Word (.docx)",
            data=docx_bytes,
            file_name=f"SRS_Document_{project_name}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
            key=f"dl_full_docx_{selected_jid}"
        )
    with exp_cols[2]:
        audit_report = assembler.generate_verification_report(verification_reports)
        st.download_button(
            label="🛡️ Audit Report (.md)",
            data=audit_report,
            file_name=f"SRS_Verification_Report_{project_name}.md",
            mime="text/markdown",
            use_container_width=True,
            key=f"dl_audit_report_{selected_jid}"
        )
    with exp_cols[3]:
        canonical_text = json.dumps(canonical, indent=2)
        st.download_button(
            label="🔒 Canonical Data (.json)",
            data=canonical_text,
            file_name=f"canonical_requirements_{project_name}.json",
            mime="application/json",
            use_container_width=True,
            key=f"dl_canonical_{selected_jid}"
        )

    st.markdown("---")

    # Split into preview and audit tabs
    sub_tab_preview, sub_tab_audit = st.tabs(["📖 Full Document Viewer", "🛡️ Verification Audit Dashboard"])

    with sub_tab_preview:
        # Table of contents
        st.markdown("#### 📑 Table of Contents")
        for sec_num, sec_title in stages.SRS_SECTIONS:
            sec_key = f"{sec_num}_sec"
            is_done = sec_key in srs_sections and bool(srs_sections[sec_key].strip())
            status = "✅" if is_done else "⬜"
            st.markdown(f"{status} **{sec_num}. {sec_title}**")
            
        st.markdown("---")
        st.markdown("#### 📖 Document Body")
        
        # Render each section inside expanders
        for sec_num, sec_title in stages.SRS_SECTIONS:
            sec_key = f"{sec_num}_sec"
            if sec_key in srs_sections and srs_sections[sec_key].strip():
                content = srs_sections[sec_key]
                with st.expander(f"📝 {sec_num}. {sec_title}", expanded=False):
                    st.markdown(content)
                    
                    col_sec_dl, col_sec_raw = st.columns(2)
                    with col_sec_dl:
                        assembler_safe_title = sec_title.replace(" ", "_").replace(".", "")
                        st.download_button(
                            label="⬇️ Download Section",
                            data=content,
                            file_name=f"SRS_Section_{sec_num}_{assembler_safe_title}.md",
                            mime="text/markdown",
                            key=f"preview_dl_{sec_num}_{selected_jid}"
                        )
                    with col_sec_raw:
                        if st.button("📋 Show Raw Text", key=f"preview_raw_{sec_num}_{selected_jid}"):
                            st.code(content)

    with sub_tab_audit:
        if not verification_reports:
            st.info("No verification audit compiled for this job.")
        else:
            st.markdown(assembler.generate_verification_report(verification_reports))
