# tab_generate.py — Tab 2: Multi-Job Dashboard & Live Tracker

import streamlit as st
import time
from pipeline import job_manager


def render_generate_tab(client):
    st.markdown("### 📊 Multi-Job Dashboard & Live Tracker")
    st.info("Track all active and past SRS generation jobs. Jobs run hands-free in the background, persistent across page refreshes, with GPU concurrency control and checkpoint resume.")

    jobs = job_manager.list_all_jobs()

    if not jobs:
        st.warning("⚠️ No jobs found. Please submit a project archive in the **Submit Project Job** tab.")
        return

    # Metrics Row
    running_count = sum(1 for j in jobs if j.get("status") == "RUNNING")
    completed_count = sum(1 for j in jobs if j.get("status") == "COMPLETED")
    failed_count = sum(1 for j in jobs if j.get("status") == "FAILED")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Jobs", len(jobs))
    with c2:
        st.metric("Running ⏳", running_count)
    with c3:
        st.metric("Completed ✅", completed_count)
    with c4:
        st.metric("Failed / Interrupted ❌", failed_count)

    st.markdown("---")

    # Render each job card
    for job in jobs:
        jid = job.get("job_id", "")
        status = job.get("status", "QUEUED")
        archive_name = job.get("archive_name", "")
        progress = job.get("progress_pct", 0)
        current_stage = job.get("current_stage", "Queued")
        created_at = job.get("created_at", "")
        logs = job.get("logs", [])
        telemetry = job.get("telemetry", {})

        if status == "COMPLETED":
            badge_html = '<span class="status-badge-done">✅ COMPLETED</span>'
            card_class = "section-card section-done"
        elif status == "RUNNING":
            badge_html = f'<span class="status-badge-done" style="border-color:#3b82f6;color:#60a5fa;background:rgba(59,130,246,0.15);">⏳ {current_stage} ({progress}%)</span>'
            card_class = "section-card"
        elif status == "FAILED":
            badge_html = '<span class="status-badge-pending" style="border-color:#ef4444;color:#f87171;background:rgba(239,68,68,0.15);">❌ FAILED / INTERRUPTED</span>'
            card_class = "section-card section-pending"
        else:
            badge_html = '<span class="status-badge-pending">⏸️ QUEUED (Awaiting GPU Semaphore)</span>'
            card_class = "section-card section-pending"

        st.markdown(f'<div class="{card_class}">', unsafe_allow_html=True)
        col_j1, col_j2, col_j3 = st.columns([3, 1, 1])

        with col_j1:
            st.markdown(f"**{archive_name}** &nbsp; (`{jid}`) &nbsp; {badge_html}", unsafe_allow_html=True)
            
            # Telemetry display
            t_info = ""
            if telemetry:
                t_info = f" | Elapsed: {telemetry.get('elapsed_str', '0s')} | ETA: {telemetry.get('eta_str', 'Calculated...')}"
            
            st.caption(f"Created: {created_at} | Stage: {current_stage}{t_info}")
            st.progress(progress / 100.0)

        with col_j2:
            if status == "COMPLETED":
                if st.button("📄 View SRS", key=f"view_job_{jid}", use_container_width=True):
                    st.session_state.selected_job_for_preview = jid
                    st.success(f"Selected {archive_name}! Go to **Preview & Export SRS** tab.")
            elif status in ["FAILED", "QUEUED"]:
                if st.button("⏯️ Resume", key=f"resume_job_{jid}", use_container_width=True):
                    job_manager.resume_job(jid)
                    st.rerun()

        with col_j3:
            if st.button("🗑️ Delete", key=f"del_job_{jid}", use_container_width=True):
                job_manager.delete_job(jid)
                st.rerun()

        with st.expander("📋 Live Job Logs & Telemetry", expanded=(status == "RUNNING")):
            if logs:
                st.code("\n".join(logs[-25:]))
            if job.get("error"):
                st.error(f"Error Details: {job['error']}")

        st.markdown("</div>", unsafe_allow_html=True)

    # Auto-refresh if any job is running
    if running_count > 0:
        time.sleep(2)
        st.rerun()
