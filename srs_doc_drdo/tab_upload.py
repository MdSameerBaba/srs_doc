# tab_upload.py — Tab 1: Upload Project

import streamlit as st
import shutil
import os
import zipfile
import tarfile
from pathlib import Path
from helpers import extract_zip, extract_tar, language_counts, total_size_kb, run_pure_python_extractor
from pipeline import graph_loader as gl

def clear_directory(path: Path):
    """Safely clear a directory handling read-only files on Windows without using deprecated shutil callbacks."""
    if not path.exists():
        return
    for root, dirs, files in os.walk(path, topdown=False):
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

def render_upload_tab():
    st.markdown("### Upload Your Project Codebase")
    st.info(
        "Upload a **ZIP or TAR.GZ archive** of your project folder. "
        "The system will extract your codebase, build a structured AST code graph in SQLite, "
        "and analyze file relationships to generate a high-fidelity SRS."
    )

    col_up, col_info = st.columns([1, 1], gap="large")

    with col_up:
        archive = st.file_uploader(
            "Project Archive (ZIP / TAR.GZ)",
            type=["zip", "tar", "gz", "tgz"],
            key="project_uploader",
        )

        if archive:
            with st.spinner("🔍 Extracting, parsing AST symbols, and indexing graph..."):
                # 1. Memory-based load for backward compatibility with prompt context builder
                archive.seek(0)
                loaded = (
                    extract_zip(archive)
                    if archive.name.lower().endswith(".zip")
                    else extract_tar(archive)
                )
                
                # 2. Disk-based extraction for AST graph parser
                output_dir = Path("srs_output")
                dest_dir = output_dir / "extracted_codebase"
                clear_directory(dest_dir)
                dest_dir.mkdir(parents=True, exist_ok=True)
                
                archive.seek(0)
                try:
                    if archive.name.lower().endswith(".zip"):
                        with zipfile.ZipFile(archive, 'r') as zip_ref:
                            zip_ref.extractall(dest_dir)
                    else:
                        with tarfile.open(fileobj=archive, mode="r:*") as tar_ref:
                            tar_ref.extractall(dest_dir)
                            
                    # Resolve single nested directory
                    contents = list(dest_dir.iterdir())
                    if len(contents) == 1 and contents[0].is_dir():
                        codebase_path_resolved = contents[0]
                    else:
                        codebase_path_resolved = dest_dir
                        
                    # Save resolved path to state
                    st.session_state.codebase_path = str(codebase_path_resolved.resolve())
                    
                    # Run AST extraction
                    graph_json_path = output_dir / "graph.json"
                    run_pure_python_extractor(codebase_path_resolved, graph_json_path)
                    
                    # Load into SQLite DB
                    db_path = output_dir / "srs_graph.db"
                    if db_path.exists():
                        try:
                            db_path.unlink()
                        except Exception:
                            pass
                            
                    stats = gl.load_graph(graph_json_path, db_path)
                    st.session_state.graph_stats = stats
                    
                except Exception as e:
                    st.error(f"Error parsing codebase graph: {e}")
                    loaded = None

            if loaded:
                st.session_state.project_files = loaded
                st.session_state.srs_sections  = {}
                st.session_state.archive_name  = Path(archive.name).stem
                st.session_state.phase_1_complete = False
                st.session_state.requirements_frozen = False
                st.markdown(
                    f'<div class="strip-success">✅ Successfully loaded <strong>{len(loaded)}</strong> '
                    f'files from <strong>{archive.name}</strong> '
                    f'({total_size_kb(loaded):.1f} KB total)</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="strip-success">📊 Extracted <strong>{stats["nodes"]}</strong> code nodes '
                    f'and <strong>{stats["edges"]}</strong> relations in SQLite.</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.warning("⚠️ No supported code files found in the archive.")

    with col_info:
        if st.session_state.project_files:
            files = st.session_state.project_files
            st.markdown("### 📊 Project Analysis")
            
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.metric("Total Files", len(files))
            with col_m2:
                st.metric("Total Size", f"{total_size_kb(files):.1f} KB")
                
            if st.session_state.graph_stats:
                col_m3, col_m4 = st.columns(2)
                with col_m3:
                    st.metric("AST Code Nodes", st.session_state.graph_stats.get("nodes", 0))
                with col_m4:
                    st.metric("Dependency Edges", st.session_state.graph_stats.get("edges", 0))

            lang_data = language_counts(files)
            st.markdown("**Languages / File Types Detected:**")
            for lang, cnt in sorted(lang_data.items(), key=lambda x: -x[1]):
                bar_w = int(cnt / max(lang_data.values()) * 100)
                st.markdown(
                    f"`{lang}` — {cnt} file(s) "
                    f'<div style="background:#7c3aed;height:6px;width:{bar_w}%;border-radius:4px;margin-bottom:4px"></div>',
                    unsafe_allow_html=True
                )
        else:
            st.markdown("### 💡 Tips")
            st.markdown("""
- Compress your entire project folder into a `.zip` or `.tar.gz`.
- Include all source files: backend, frontend, configs, SQL schemas, README, etc.
- Our custom AST parser runs **100% offline** and extracts functions, classes, and call-graphs directly.
- The SQLite database maps all code relationships to enable precise, hallucination-free requirements tracing.
            """)

    if st.session_state.project_files:
        st.markdown("---")
        st.success("✅ Project loaded! Go to the **Generate Sections** tab to start building your SRS.")
