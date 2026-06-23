import streamlit as st
import os
import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from pipeline import graph_loader as gl
from pipeline import stages
from pipeline import assembler
from pipeline import ollama_client as ollama

# ─────────────────────────────────────────────────────────────
# PAGE CONFIGURATION & STYLING
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Agentic SRS Generator",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium dark theme styling
st.markdown("""
<style>
/* Gradient Title */
.main-title {
    background: linear-gradient(135deg, #a78bfa, #3b82f6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
    font-size: 2.8rem;
    margin-bottom: 0.2rem;
}
.subtitle {
    color: #94a3b8;
    font-size: 1.1rem;
    margin-bottom: 2rem;
}
/* Stat Box Styling */
.stat-box {
    background-color: #13131a;
    border: 1px solid #1e1e2f;
    border-radius: 8px;
    padding: 15px;
    text-align: center;
    box-shadow: 0 4px 6px rgba(0,0,0,0.15);
}
.stat-value {
    font-size: 1.8rem;
    font-weight: bold;
    color: #7c3aed;
}
.stat-label {
    font-size: 0.85rem;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
/* Terminal console styling */
.terminal-header {
    background-color: #1e1e2f;
    border: 1px solid #27272a;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 12px;
    font-family: monospace;
    font-size: 0.8rem;
    color: #a1a1aa;
    display: flex;
    justify-content: space-between;
}
.terminal-body {
    margin-top: 0px !important;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# SESSION STATE INITIALIZATION
# ─────────────────────────────────────────────────────────────
if "step" not in st.session_state:
    st.session_state.step = "setup"
if "logs" not in st.session_state:
    st.session_state.logs = []
if "stage_status" not in st.session_state:
    st.session_state.stage_status = {i: "pending" for i in range(7)}
if "codebase_path" not in st.session_state:
    st.session_state.codebase_path = ""
if "architecture" not in st.session_state:
    st.session_state.architecture = {}
if "canonical_requirements" not in st.session_state:
    st.session_state.canonical_requirements = {}
if "sections" not in st.session_state:
    st.session_state.sections = {}
if "verification_reports" not in st.session_state:
    st.session_state.verification_reports = {}
if "graph_stats" not in st.session_state:
    st.session_state.graph_stats = {}

# Model Configuration Defaults
if "ollama_url" not in st.session_state:
    st.session_state.ollama_url = "http://localhost:11434"
if "heavy_model" not in st.session_state:
    st.session_state.heavy_model = "gpt-oss-20b"
if "fast_model" not in st.session_state:
    st.session_state.fast_model = "gemma3n:e4b"
if "concurrency" not in st.session_state:
    st.session_state.concurrency = 3

# ─────────────────────────────────────────────────────────────
# LOGGING HELPER
# ─────────────────────────────────────────────────────────────
def add_log(message: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{timestamp}] {message}")

# ─────────────────────────────────────────────────────────────
# OLLAMA CONFIGURATION & STATUS SIDEBAR
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Engine Settings")
    st.session_state.ollama_url = st.text_input(
        "Ollama Server URL",
        value=st.session_state.ollama_url
    )
    
    # Check Connection
    is_connected, status_msg = ollama.check_connection(st.session_state.ollama_url)
    if is_connected:
        st.success(status_msg)
        # Load available models
        available_models = ollama.list_models(st.session_state.ollama_url)
        
        # Heavy Model selector
        default_heavy = st.session_state.heavy_model
        heavy_options = available_models.copy()
        if default_heavy not in heavy_options:
            heavy_options.insert(0, default_heavy)
        st.session_state.heavy_model = st.selectbox(
            "Heavy Model (A, C, D, E, F)",
            options=heavy_options,
            index=heavy_options.index(default_heavy)
        )
        
        # Fast Model selector
        default_fast = st.session_state.fast_model
        fast_options = available_models.copy()
        if default_fast not in fast_options:
            fast_options.insert(0, default_fast)
        st.session_state.fast_model = st.selectbox(
            "Fast Model (B)",
            options=fast_options,
            index=fast_options.index(default_fast)
        )
    else:
        st.error(status_msg)
        st.session_state.heavy_model = st.text_input("Heavy Model Override", value=st.session_state.heavy_model)
        st.session_state.fast_model = st.text_input("Fast Model Override", value=st.session_state.fast_model)
        
    st.session_state.concurrency = st.slider(
        "Stage B Concurrency (workers)",
        min_value=1,
        max_value=10,
        value=st.session_state.concurrency
    )
    
    st.markdown("---")
    
    # Progress visualization sidebar
    st.markdown("### 🗺️ Pipeline Progress")
    stages_info = [
        (0, "Stage 0: AST Graph Extraction"),
        (1, "Stage 1: Architecture Snapshot (Prompt A)"),
        (2, "Stage 2: Leaf Node Summarization (Prompt B)"),
        (3, "Stage 3: Module / Subsystem Rollup (Prompt C)"),
        (4, "Stage 4: Requirement Extraction (Prompt D)"),
        (5, "Stage 5: SRS Section Writing (Prompt E)"),
        (6, "Stage 6: Adversarial Verification (Prompt F)"),
    ]
    for num, name in stages_info:
        status = st.session_state.stage_status[num]
        if status == "pending":
            st.markdown(f"⚪ **{name}** — *Pending*")
        elif status == "running":
            st.markdown(f"🔵 **{name}** — *Running...*")
        elif status == "complete":
            st.markdown(f"✅ **{name}** — *Complete*")
        elif status == "failed":
            st.markdown(f"❌ **{name}** — *Failed*")

# ─────────────────────────────────────────────────────────────
# PIPELINE EXECUTION ENGINE
# ─────────────────────────────────────────────────────────────
def execute_phase_1(codebase_path: Path, config: dict, status_container, log_placeholder, progress_placeholder):
    st.session_state.logs = []
    add_log("🚀 Initializing Pipeline Phase 1 (Extraction & Synthesis)...")
    log_placeholder.code("\n".join(st.session_state.logs[-15:]))
    
    # ── STAGE 0: Graphify AST Extraction ──────────────────
    st.session_state.stage_status[0] = "running"
    add_log("Stage 0: Running Graphify AST extraction on codebase...")
    log_placeholder.code("\n".join(st.session_state.logs[-15:]))
    
    try:
        # Run python -m graphify update . with Cwd=codebase_path
        cmd = [sys.executable, "-m", "graphify", "update", "."]
        add_log(f"Executing command: {' '.join(cmd)}")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
        
        res = subprocess.run(
            cmd,
            cwd=str(codebase_path),
            capture_output=True,
            text=True,
            check=True
        )
        add_log("✅ Graphify AST extraction complete.")
        # Feed stdout to log
        for line in res.stdout.splitlines():
            if line.strip():
                add_log(line)
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
        
        graph_json_path = codebase_path / "graphify-out" / "graph.json"
        if not graph_json_path.exists():
            raise FileNotFoundError(f"Expected graph.json at {graph_json_path}")
            
        # Clear/Create Database
        output_dir = codebase_path / "srs_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        db_path = output_dir / "srs_graph.db"
        if db_path.exists():
            add_log("Clearing existing SQLite graph database...")
            try:
                db_path.unlink()
            except Exception as e:
                add_log(f"Warning: Could not delete old DB: {e}")
            
        add_log(f"Loading graphify output into SQLite DB at {db_path}...")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
        
        stats = gl.load_graph(graph_json_path, db_path)
        st.session_state.graph_stats = stats
        st.session_state.stage_status[0] = "complete"
        add_log(f"✅ Graph loaded. Stats: {stats['nodes']} nodes, {stats['edges']} edges, {stats['files']} files.")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
        
    except Exception as e:
        st.session_state.stage_status[0] = "failed"
        add_log(f"❌ Stage 0 failed: {e}")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
        st.session_state.step = "setup"
        return False

    # ── STAGE 1: Architecture Snapshot ──────────────────
    st.session_state.stage_status[1] = "running"
    add_log("Stage 1: Building Architecture Snapshot (Prompt A)...")
    log_placeholder.code("\n".join(st.session_state.logs[-15:]))
    try:
        arch = stages.run_stage_a(db_path, codebase_path, config, add_log)
        st.session_state.architecture = arch
        st.session_state.stage_status[1] = "complete"
        add_log("✅ Stage 1 complete.")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
    except Exception as e:
        st.session_state.stage_status[1] = "failed"
        add_log(f"❌ Stage 1 failed: {e}")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
        st.session_state.step = "setup"
        return False

    # ── STAGE 2: Leaf Node Summarization ──────────────────
    st.session_state.stage_status[2] = "running"
    add_log("Stage 2: Running Leaf Node Summarization (Prompt B)...")
    log_placeholder.code("\n".join(st.session_state.logs[-15:]))
    try:
        def stage_b_progress(completed, total):
            pct = completed / total if total > 0 else 0
            progress_placeholder.progress(pct, text=f"Summarized {completed}/{total} leaf nodes...")
            
        stages.run_stage_b(db_path, codebase_path, config, add_log, stage_b_progress)
        progress_placeholder.empty()
        st.session_state.stage_status[2] = "complete"
        add_log("✅ Stage 2 complete.")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
    except Exception as e:
        st.session_state.stage_status[2] = "failed"
        add_log(f"❌ Stage 2 failed: {e}")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
        st.session_state.step = "setup"
        return False

    # ── STAGE 3: Module Rollup ──────────────────
    st.session_state.stage_status[3] = "running"
    add_log("Stage 3: Running Module Rollups (Prompt C)...")
    log_placeholder.code("\n".join(st.session_state.logs[-15:]))
    try:
        def stage_c_progress(completed, total):
            pct = completed / total if total > 0 else 0
            progress_placeholder.progress(pct, text=f"Rolled up {completed}/{total} modules...")
            
        stages.run_stage_c(db_path, config, add_log, stage_c_progress)
        progress_placeholder.empty()
        st.session_state.stage_status[3] = "complete"
        add_log("✅ Stage 3 complete.")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
    except Exception as e:
        st.session_state.stage_status[3] = "failed"
        add_log(f"❌ Stage 3 failed: {e}")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
        st.session_state.step = "setup"
        return False

    # ── STAGE 4: Requirement Extraction (Freeze Point) ──
    st.session_state.stage_status[4] = "running"
    add_log("Stage 4: Extracting requirements & freezing canonical schema (Prompt D)...")
    log_placeholder.code("\n".join(st.session_state.logs[-15:]))
    try:
        reqs = stages.run_stage_d(st.session_state.architecture, db_path, config, add_log)
        st.session_state.canonical_requirements = reqs
        st.session_state.stage_status[4] = "complete"
        add_log("✅ Stage 4 complete. Transitioning to Requirements Freeze Gate.")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
        
        # Write requirements to disk initially
        canonical_path = output_dir / "canonical.json"
        if canonical_path.exists():
            try:
                os.chmod(canonical_path, 0o666)  # ensure writable
            except Exception:
                pass
        with open(canonical_path, "w", encoding="utf-8") as f:
            json.dump(reqs, f, indent=2)
            
        st.session_state.step = "freeze_checkpoint"
        return True
    except Exception as e:
        st.session_state.stage_status[4] = "failed"
        add_log(f"❌ Stage 4 failed: {e}")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
        st.session_state.step = "setup"
        return False


def execute_phase_2(codebase_path: Path, config: dict, status_container, log_placeholder, progress_placeholder):
    add_log("🚀 Initializing Pipeline Phase 2 (Writing & Verification)...")
    st.session_state.stage_status[5] = "running"
    st.session_state.stage_status[6] = "running"
    log_placeholder.code("\n".join(st.session_state.logs[-15:]))
    
    output_dir = codebase_path / "srs_output"
    
    try:
        # Load canonical JSON from file to ensure we use the frozen version
        canonical_path = output_dir / "canonical.json"
        with open(canonical_path, "r", encoding="utf-8") as f:
            canonical = json.load(f)
            
        sections_md = {}
        reports = {}
        total_sections = len(stages.SRS_SECTIONS)
        completed_sections = 0
        
        def process_section(sec_num, sec_title):
            add_log(f"Starting pipeline for Section {sec_num}: {sec_title}")
            # Stage E: Write
            md = stages.run_stage_e(canonical, sec_num, sec_title, config, add_log)
            # Stage F: Audit
            final_md, report = stages.run_stage_f(canonical, md, sec_num, sec_title, config, add_log)
            return sec_num, final_md, report
            
        workers = max(1, min(config.get("concurrency", 3), total_sections))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_section, num, title): (num, title) for num, title in stages.SRS_SECTIONS}
            for future in as_completed(futures):
                num, title = futures[future]
                try:
                    sec_num, final_md, report = future.result()
                    sections_md[sec_num] = final_md
                    reports[sec_num] = report
                except Exception as e:
                    add_log(f"❌ Section {num} failed: {e}")
                    sections_md[num] = f"## {num}. {title}\n\n[Failed to generate due to error: {e}]"
                    reports[num] = {"status": "FAIL", "error": str(e)}
                
                completed_sections += 1
                pct = completed_sections / total_sections
                progress_placeholder.progress(pct, text=f"Generated and verified {completed_sections}/{total_sections} sections...")
                log_placeholder.code("\n".join(st.session_state.logs[-15:]))
                
        progress_placeholder.empty()
        st.session_state.sections = sections_md
        st.session_state.verification_reports = reports
        
        st.session_state.stage_status[5] = "complete"
        st.session_state.stage_status[6] = "complete"
        
        # Assemble Final SRS Document
        add_log("Stitching SRS sections together...")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
        project_name = codebase_path.name
        final_srs = assembler.assemble_srs(sections_md, canonical, project_name)
        srs_path = output_dir / "SRS_final.md"
        with open(srs_path, "w", encoding="utf-8") as f:
            f.write(final_srs)
        add_log(f"✅ Final SRS written to {srs_path}")
        
        # Generate Audit Report
        audit_report = assembler.generate_verification_report(reports)
        audit_path = output_dir / "audit_report.md"
        with open(audit_path, "w", encoding="utf-8") as f:
            f.write(audit_report)
        add_log(f"✅ Audit report written to {audit_path}")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
        
        st.session_state.step = "complete"
        add_log("🎉 Pipeline execution completed successfully!")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
        return True
        
    except Exception as e:
        st.session_state.stage_status[5] = "failed"
        st.session_state.stage_status[6] = "failed"
        add_log(f"❌ Phase 2 failed: {e}")
        log_placeholder.code("\n".join(st.session_state.logs[-15:]))
        st.session_state.step = "setup"
        return False

# ─────────────────────────────────────────────────────────────
# MAIN APPLICATION VIEW
# ─────────────────────────────────────────────────────────────

# HEADER
st.markdown("<div class='main-title'>🧠 Agentic SRS Generator</div>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>Automate Software Requirements Specification directly from codebase graphs with audit reports</div>", unsafe_allow_html=True)

config = {
    "heavy_model": st.session_state.heavy_model,
    "fast_model": st.session_state.fast_model,
    "ollama_url": st.session_state.ollama_url,
    "concurrency": st.session_state.concurrency,
}

# --- PAGE 1: SETUP & GRAPH CONFIGURATION ---
if st.session_state.step == "setup":
    st.markdown("### 📁 Codebase Configuration")
    
    codebase_input = st.text_input(
        "Absolute path to local codebase folder",
        value=st.session_state.codebase_path,
        placeholder="C:\\Users\\username\\projects\\my-app"
    )
    
    col1, col2 = st.columns([1, 4])
    with col1:
        start_btn = st.button("▶️ Generate SRS", use_container_width=True)
    
    if start_btn:
        if not codebase_input:
            st.error("Please enter a codebase folder path.")
        else:
            p = Path(codebase_input)
            if not p.is_dir():
                st.error("The specified path does not exist or is not a directory.")
            else:
                st.session_state.codebase_path = str(p.resolve())
                st.session_state.step = "running_phase_1"
                # Reset statuses
                st.session_state.stage_status = {i: "pending" for i in range(7)}
                st.session_state.logs = []
                st.rerun()

# --- PAGE 2: PIPELINE RUNNING (PHASE 1) ---
elif st.session_state.step == "running_phase_1":
    st.markdown("### 🔄 Phase 1: Analyzing and Synthesizing Code Graph")
    
    # Terminals and progress bars
    status_container = st.empty()
    progress_placeholder = st.empty()
    
    st.markdown("<div class='terminal-header'><span>Console Output</span><span>bash</span></div>", unsafe_allow_html=True)
    log_placeholder = st.empty()
    
    # Run pipeline phase 1
    with st.spinner("Executing Phase 1 (Stages 0 to 4)..."):
        success = execute_phase_1(
            Path(st.session_state.codebase_path),
            config,
            status_container,
            log_placeholder,
            progress_placeholder
        )
        if success:
            st.rerun()
        else:
            st.error("Pipeline failed during Phase 1. Please check the logs.")
            if st.button("Return to Setup"):
                st.session_state.step = "setup"
                st.rerun()

# --- PAGE 3: REQUIREMENTS FREEZE GATE ---
elif st.session_state.step == "freeze_checkpoint":
    st.markdown("### 🔒 Freeze Gate: Canonical Requirements Verification")
    st.warning("Requirements have been successfully extracted from your codebase! Please review and modify them below if necessary. Once approved, the requirements will be frozen as read-only, and Phase 2 (Section writing) will proceed.")
    
    output_dir = Path(st.session_state.codebase_path) / "srs_output"
    canonical_path = output_dir / "canonical.json"
    
    # Load requirements from disk
    try:
        with open(canonical_path, "r", encoding="utf-8") as f:
            reqs_json_text = f.read()
    except Exception as e:
        reqs_json_text = json.dumps(st.session_state.canonical_requirements, indent=2)
        
    edited_json_text = st.text_area(
        "Canonical Requirements JSON",
        value=reqs_json_text,
        height=450,
        help="Edit the actors, functional requirements, or non-functional signals before generating the SRS."
    )
    
    col1, col2, col3 = st.columns([1.5, 1.5, 4])
    with col1:
        approve_btn = st.button("🔒 Approve & Freeze", type="primary", use_container_width=True)
    with col2:
        cancel_btn = st.button("❌ Abort Generation", use_container_width=True)
        
    if approve_btn:
        try:
            parsed_json = json.loads(edited_json_text)
            
            # Make sure writable
            if canonical_path.exists():
                try:
                    os.chmod(canonical_path, 0o666)
                except Exception:
                    pass
            
            # Save the approved JSON
            with open(canonical_path, "w", encoding="utf-8") as f:
                json.dump(parsed_json, f, indent=2)
                
            # Freeze the file (read-only)
            try:
                os.chmod(canonical_path, 0o444)
                add_log("Canonical requirements file locked (read-only).")
            except Exception as e:
                add_log(f"Warning: Could not make file read-only: {e}")
                
            st.session_state.canonical_requirements = parsed_json
            st.session_state.step = "running_phase_2"
            st.rerun()
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {e}. Please correct formatting errors before freezing.")
            
    if cancel_btn:
        st.session_state.step = "setup"
        st.rerun()

# --- PAGE 4: PIPELINE RUNNING (PHASE 2) ---
elif st.session_state.step == "running_phase_2":
    st.markdown("### 🔄 Phase 2: Document Generation & Auditing")
    
    status_container = st.empty()
    progress_placeholder = st.empty()
    
    st.markdown("<div class='terminal-header'><span>Console Output</span><span>bash</span></div>", unsafe_allow_html=True)
    log_placeholder = st.empty()
    
    with st.spinner("Writing and auditing SRS sections in parallel..."):
        success = execute_phase_2(
            Path(st.session_state.codebase_path),
            config,
            status_container,
            log_placeholder,
            progress_placeholder
        )
        if success:
            st.rerun()
        else:
            st.error("Pipeline failed during Phase 2. Please check the logs.")
            if st.button("Return to Setup"):
                st.session_state.step = "setup"
                st.rerun()

# --- PAGE 5: COMPLETE & REVIEW & DOWNLOAD ---
elif st.session_state.step == "complete":
    st.markdown("### 🎉 Software Requirements Specification Generation Complete")
    
    output_dir = Path(st.session_state.codebase_path) / "srs_output"
    srs_path = output_dir / "SRS_final.md"
    audit_path = output_dir / "audit_report.md"
    canonical_path = output_dir / "canonical.json"
    
    # Read generated documents
    srs_content = ""
    if srs_path.exists():
        with open(srs_path, "r", encoding="utf-8") as f:
            srs_content = f.read()
            
    audit_content = ""
    if audit_path.exists():
        with open(audit_path, "r", encoding="utf-8") as f:
            audit_content = f.read()
            
    canonical_content = ""
    if canonical_path.exists():
        with open(canonical_path, "r", encoding="utf-8") as f:
            canonical_content = f.read()
            
    # Stats row
    st.markdown("#### 📊 Project Statistics")
    stats_cols = st.columns(4)
    with stats_cols[0]:
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-value">{st.session_state.graph_stats.get('nodes', 0)}</div>
            <div class="stat-label">Code Nodes</div>
        </div>
        """, unsafe_allow_html=True)
    with stats_cols[1]:
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-value">{st.session_state.graph_stats.get('edges', 0)}</div>
            <div class="stat-label">Graph Edges</div>
        </div>
        """, unsafe_allow_html=True)
    with stats_cols[2]:
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-value">{len(st.session_state.canonical_requirements.get('functional_requirements', []))}</div>
            <div class="stat-label">Extracted FRs</div>
        </div>
        """, unsafe_allow_html=True)
    with stats_cols[3]:
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-value">{len(st.session_state.canonical_requirements.get('non_functional_signals', []))}</div>
            <div class="stat-label">NFR Signals</div>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown("---")
    
    # Download Buttons Row
    st.markdown("#### 📥 Exports")
    download_cols = st.columns(4)
    with download_cols[0]:
        st.download_button(
            "📄 Download SRS Document (.md)",
            data=srs_content,
            file_name="SRS_final.md",
            mime="text/markdown",
            use_container_width=True
        )
    with download_cols[1]:
        st.download_button(
            "🛡️ Download Verification Report (.md)",
            data=audit_content,
            file_name="audit_report.md",
            mime="text/markdown",
            use_container_width=True
        )
    with download_cols[2]:
        st.download_button(
            "🔒 Download Canonical JSON (.json)",
            data=canonical_content,
            file_name="canonical.json",
            mime="application/json",
            use_container_width=True
        )
    with download_cols[3]:
        if st.button("🔄 Generate Another Document", use_container_width=True):
            st.session_state.step = "setup"
            st.session_state.stage_status = {i: "pending" for i in range(7)}
            st.session_state.logs = []
            st.rerun()
            
    st.markdown("---")
    
    # Tabs for preview
    tab1, tab2, tab3 = st.tabs(["📄 SRS Document Preview", "🛡️ Verification Audit Report", "🔒 Canonical Requirements"])
    
    with tab1:
        st.markdown(srs_content or "*No SRS content generated yet.*")
        
    with tab2:
        st.markdown(audit_content or "*No audit report generated yet.*")
        
    with tab3:
        st.json(st.session_state.canonical_requirements)
