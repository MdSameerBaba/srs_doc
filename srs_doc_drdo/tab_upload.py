# tab_upload.py — Tab 1: Submit Project Job (Upload)

import streamlit as st
from pathlib import Path
from constants import SUPPORTED_EXTENSIONS, DEFAULT_INCLUDED_EXTENSIONS
from pipeline import job_manager


def render_upload_tab():
    st.markdown("### 🚀 Submit Project Codebase Job")
    st.info(
        "Upload a **ZIP or TAR.GZ archive** of your project folder. "
        "The system will create an isolated background job, extract your codebase, build a structured AST code graph in SQLite, "
        "and automatically run the hands-free SRS pipeline."
    )

    col_up, col_info = st.columns([1, 1], gap="large")

    with col_up:
        # ── Extension Multi-Select Dropdown Option Menu ──
        all_ext_options = sorted(list(SUPPORTED_EXTENSIONS.keys()))
        default_selected = [ext for ext in DEFAULT_INCLUDED_EXTENSIONS if ext in SUPPORTED_EXTENSIONS]

        st.session_state.include_extensions = st.multiselect(
            "Select File Types / Extensions to Include",
            options=all_ext_options,
            default=st.session_state.get("include_extensions", default_selected),
            format_func=lambda ext: f"{ext}  ({SUPPORTED_EXTENSIONS.get(ext, ext)})",
            help="Select which file extensions to include in the analysis.",
            key="include_extensions_multiselect",
        )

        archive = st.file_uploader(
            "Project Archive (ZIP / TAR.GZ)",
            type=["zip", "tar", "gz", "tgz"],
            key="project_uploader",
        )

        if archive:
            st.success(f"📦 Archive selected: **{archive.name}** ({archive.size / 1024:.1f} KB)")
            
            submit_btn = st.button("🚀 Submit Job & Run Background Pipeline", type="primary", use_container_width=True)

            if submit_btn:
                archive.seek(0)
                bytes_data = archive.read()
                
                incl_list = st.session_state.get("include_extensions", default_selected)
                config = {
                    "heavy_model": st.session_state.current_model,
                    "fast_model": st.session_state.get("fast_model", "qwen3:latest"),
                    "ollama_url": st.session_state.ollama_host,
                    "concurrency": st.session_state.get("concurrency", 3),
                    "enable_audit": st.session_state.get("enable_audit", False),
                    "num_ctx": st.session_state.get("num_ctx", 64000),
                    "file_level_summarization": st.session_state.get("file_level_summarization", False),
                    "llm_provider": st.session_state.get("llm_provider", "ollama"),
                    "gemini_api_key": st.session_state.get("gemini_api_key", ""),
                }

                with st.spinner("Submitting job to background runner..."):
                    job_id = job_manager.create_job(archive.name, bytes_data, incl_list, config)
                    st.session_state.active_job_id = job_id
                    st.success(f"🎉 Job **{job_id}** submitted successfully! Go to the **Multi-Job Dashboard** tab to track live progress.")

    with col_info:
        st.markdown("### 💡 Highlights")
        st.markdown("""
- **Isolated Multi-Project Storage:** Every uploaded archive gets its own isolated directory on disk (`srs_output/jobs/<job_id>/`). Old uploads never interfere with new ones!
- **Persistent Background Processing:** Runs in background threads. You can close or refresh your browser tab anytime without interrupting running jobs!
- **Hands-Free Pipeline:** Automatically runs AST extraction $\rightarrow$ Code Summarization $\rightarrow$ Module Rollups $\rightarrow$ Requirements Freeze $\rightarrow$ SRS Section Writing $\rightarrow$ Final Assembly.
- **Multiple Parallel Jobs:** Upload multiple projects in parallel or sequentially. Track all active and completed jobs in the **Multi-Job Dashboard**.
        """)
