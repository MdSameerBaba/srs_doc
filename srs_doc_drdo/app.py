import streamlit as st
from pathlib import Path
from tab_upload   import render_upload_tab
from tab_generate import render_generate_tab
from tab_preview  import render_preview_tab
from pipeline import ollama_client as ollama

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SRS Report Generator",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Premium dark theme styling injection
st.markdown("""
<style>
/* Gradient Header */
.title-header {
    background: linear-gradient(135deg, #a78bfa, #3b82f6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
    text-align: center;
    font-size: 4.5rem;
    margin-bottom: 0.2rem;
    text-shadow: 0 0 20px rgba(124, 58, 237, 0.2);
}

/* Custom Cards */
.section-card {
    background-color: #13131a;
    border: 1px solid #1e1e2f;
    border-radius: 8px;
    padding: 18px;
    margin-bottom: 12px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.15);
}
.section-done {
    border-left: 5px solid #10b981 !important;
}
.section-pending {
    border-left: 5px solid #4b5563 !important;
}

/* Status Badges */
.status-badge-done {
    background-color: rgba(16, 185, 129, 0.15);
    color: #10b981;
    border: 1px solid #10b981;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: bold;
}
.status-badge-pending {
    background-color: rgba(107, 114, 128, 0.15);
    color: #9ca3af;
    border: 1px solid #6b7280;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: bold;
}

/* Strip Alerts */
.strip-success {
    background-color: rgba(16, 185, 129, 0.1);
    border: 1px solid rgba(16, 185, 129, 0.2);
    color: #e2e8f0;
    padding: 10px 15px;
    border-radius: 6px;
    margin-top: 10px;
    margin-bottom: 10px;
}
</style>
""", unsafe_allow_html=True)

# ─── Session State ────────────────────────────────────────────────────────────
_default_gemini_key = st.secrets.get("gemini_api_key", "")

def init_state():
    defaults = {
        "project_files":          {},
        "srs_sections":           {},
        "generation_order":       [],
        "ollama_host":            "http://127.0.0.1:11434",
        "current_model":          "qwen3:latest",
        "fast_model":             "qwen3:latest",
        "concurrency":            3,
        "active_tab":             "upload",
        "full_srs_doc":           "",
        "stage_status":           {i: "pending" for i in range(7)},
        "logs":                   [],
        "graph_stats":            {},
        "codebase_path":          "",
        "architecture":           {},
        "canonical_requirements":  {},
        "verification_reports":   {},
        # Default to Ollama; switch to Gemini manually via sidebar radio
        "llm_provider":           "ollama",
        "gemini_api_key":         _default_gemini_key,
        "enable_audit":           False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# (Provider is set from init_state defaults — no Ollama ping needed)

# ─── Sidebar Engine Settings ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Engine Settings")

    # ── LLM Provider selector ──
    st.session_state.llm_provider = st.radio(
        "LLM Provider",
        options=["ollama", "gemini"],
        index=0 if st.session_state.llm_provider == "ollama" else 1,
        horizontal=True,
        key="llm_provider_radio"
    )

    if st.session_state.llm_provider == "gemini":
        st.session_state.gemini_api_key = st.text_input(
            "Gemini API Key",
            value=st.session_state.gemini_api_key,
            type="password",
            placeholder="AIza...",
            key="gemini_api_key_input"
        )
        # Show fixed model info
        st.info(
            "🔵 **Heavy stages (A/C/D/E/F):** gemini-2.5-pro\n\n"
            "⚡ **Fast stage (B):** gemini-2.5-flash",
            icon=None
        )
    else:
        st.session_state.ollama_host = st.text_input(
            "Ollama Server URL",
            value=st.session_state.ollama_host,
            key="ollama_host_input"
        )

        # Check Connection and auto-detect models
        is_connected, status_msg = ollama.check_connection(st.session_state.ollama_host)
        if is_connected:
            st.success(status_msg)
            available_models = ollama.list_models(st.session_state.ollama_host)

            # Heavy Model selector
            default_heavy = st.session_state.current_model
            heavy_options = available_models.copy()
            if default_heavy not in heavy_options:
                heavy_options.insert(0, default_heavy)
            st.session_state.current_model = st.selectbox(
                "Heavy Model (A, C, D, E, F)",
                options=heavy_options,
                index=heavy_options.index(default_heavy),
                key="heavy_model_select"
            )

            # Fast Model selector
            default_fast = st.session_state.fast_model
            fast_options = available_models.copy()
            if default_fast not in fast_options:
                fast_options.insert(0, default_fast)
            st.session_state.fast_model = st.selectbox(
                "Fast Model (B)",
                options=fast_options,
                index=fast_options.index(default_fast),
                key="fast_model_select"
            )
        else:
            st.error(status_msg)
            st.session_state.current_model = st.text_input(
                "Heavy Model Override",
                value=st.session_state.current_model,
                key="heavy_model_manual"
            )
            st.session_state.fast_model = st.text_input(
                "Fast Model Override",
                value=st.session_state.fast_model,
                key="fast_model_manual"
            )

    st.session_state.concurrency = st.slider(
        "Stage B Concurrency (workers)",
        min_value=1,
        max_value=10,
        value=st.session_state.concurrency,
        key="concurrency_slider"
    )

    st.session_state.enable_audit = st.toggle(
        "Enable Traceability Audit (Stage F)",
        value=st.session_state.enable_audit,
        help="Audits generated sections against requirements. Disabling this speeds up generation by 3x by bypassing self-correction loops.",
        key="enable_audit_toggle"
    )
    
    st.markdown("---")

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown(""" <div class="title-header">SRS Document Generation</div> """, unsafe_allow_html=True)

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_upload, tab_generate, tab_preview = st.tabs([
    "📁  Upload Project",
    "⚡  Generate Sections",
    "📄  Preview & Export",
])

with tab_upload:
    render_upload_tab()

with tab_generate:
    # Pass None as client since our pipeline uses our HTTP client directly
    render_generate_tab(None)

with tab_preview:
    render_preview_tab()
