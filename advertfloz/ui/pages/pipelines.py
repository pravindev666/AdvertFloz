"""Pipelines Management (Publishing Pipelines & Execution Status).

Exposes clear operational status for multi-campaign pipelines without requiring
users to navigate infrastructure complexities. Safe retries, sync, and execution tracking.
"""
from __future__ import annotations

from datetime import datetime, timezone
import streamlit as st

from advertfloz.domain.enums import JobStatus, Platform
from advertfloz.infrastructure.worker_client import (
    call_worker,
    delete_worker_campaign,
    fetch_worker_jobs,
    trigger_worker_tick,
)
from advertfloz.ui.components.status import chip
from advertfloz.ui.runtime import get_repo, get_settings


def render() -> None:
    settings = get_settings()
    repo = get_repo()

    st.markdown('<div class="afz-page-title">⚙️ Publishing Pipelines</div>', unsafe_allow_html=True)
    st.caption(
        "Monitor execution progress, upcoming runs, and delivery status across your active publishing pipelines."
    )

    # Sync live state from Cloudflare D1 on first load
    if settings.worker_configured and not st.session_state.get("pipelines_synced"):
        fetch_worker_jobs(repo, settings)
        st.session_state["pipelines_synced"] = True

    campaigns = repo.list_campaigns()
    camp_ids = [c.campaign_id for c in campaigns]

    if not camp_ids:
        st.info("No active publishing pipelines found. Use **Quick Campaign** to create your first pipeline.")
        if st.button("➕ Create Quick Campaign", type="primary"):
            st.switch_page("advertfloz/ui/pages/quick_campaign.py")
        return

    # Pipeline selection
    if "selected_pipeline_id" not in st.session_state or st.session_state["selected_pipeline_id"] not in camp_ids:
        st.session_state["selected_pipeline_id"] = camp_ids[-1]

    current_id = st.session_state["selected_pipeline_id"]

    c_sel, c_act1, c_act2 = st.columns([3, 1.2, 1.2])
    with c_sel:
        idx = camp_ids.index(current_id) if current_id in camp_ids else 0
        selected = st.selectbox(
            "Select Pipeline",
            options=camp_ids,
            index=idx,
            format_func=lambda cid: f"📦 {next((c.name for c in campaigns if c.campaign_id == cid), cid)} ({cid})",
            key="pipeline_selector",
        )
        if selected != current_id:
            st.session_state["selected_pipeline_id"] = selected
            st.rerun()

    with c_act1:
        st.write("")
        st.write("")
        if st.button("🔄 Sync with Cloudflare", use_container_width=True, help="Fetch latest execution status from D1"):
            with st.spinner("Syncing status from Cloudflare…"):
                fetch_worker_jobs(repo, settings)
            st.success("Synced!")
            st.rerun()

    with c_act2:
        st.write("")
        st.write("")
        if st.button("🗑️ Delete Pipeline", type="secondary", use_container_width=True):
            with st.spinner(f"Removing pipeline '{current_id}'…"):
                repo.delete_campaign(current_id)
                delete_worker_campaign(settings, current_id)
                rem = repo.list_campaigns()
                st.session_state["selected_pipeline_id"] = rem[-1].campaign_id if rem else ""
            st.success("Pipeline deleted.")
            st.rerun()

    active_id = st.session_state["selected_pipeline_id"]
    if not active_id:
        st.rerun()
        return

    campaign = repo.get_campaign(active_id)
    jobs = repo.list_jobs(campaign_id=active_id)

    # Calculate operational metrics
    total = len(jobs)
    published = sum(1 for j in jobs if j.status is JobStatus.PUBLISHED)
    queued = sum(1 for j in jobs if j.status in {JobStatus.QUEUED, JobStatus.APPROVED, JobStatus.DRAFT, JobStatus.READY_FOR_REVIEW})
    failed = sum(1 for j in jobs if j.status in {JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_PERMANENT})
    paused = sum(1 for j in jobs if j.status is JobStatus.PAUSED)

    # Determine runs
    published_jobs = [j for j in jobs if j.status is JobStatus.PUBLISHED and j.updated_at]
    last_success = max((j.updated_at for j in published_jobs), default="None yet")

    due_jobs = sorted([j for j in jobs if j.status in {JobStatus.QUEUED, JobStatus.APPROVED}], key=lambda x: str(x.scheduled_at))
    next_run = due_jobs[0].scheduled_at if due_jobs else "All completed"

    st.markdown("---")

    # Metrics Strip
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Posts", total)
    m2.metric("Scheduled / Queued", queued)
    m3.metric("Published", published)
    m4.metric("Failed", failed)
    m5.metric("Next Due", str(next_run)[:16] if next_run != "All completed" else "None")

    # Visual Progress Bar
    if total > 0:
        ratio = published / total
        bar_text = f"{published} of {total} posts published ({ratio:.0%})"
        st.progress(ratio, text=bar_text)

    # Operational Controls
    st.markdown("### ⚡ Operational Controls")
    ctl1, ctl2, ctl3 = st.columns(3)

    with ctl1:
        if st.button("⚡ Publish Due Posts Now", type="primary", use_container_width=True, help="Trigger immediate delivery for any posts whose schedule has arrived"):
            with st.spinner("Dispatching worker tick…"):
                trigger_worker_tick(settings)
                fetch_worker_jobs(repo, settings)
            st.success("Worker triggered.")
            st.rerun()

    with ctl2:
        can_retry = failed > 0
        if st.button("🔁 Safe Retry Failed Posts", disabled=not can_retry, use_container_width=True, help="Re-queue failed posts safely with incremented attempt counter"):
            with st.spinner("Re-queueing failed posts…"):
                retry_count = 0
                for j in jobs:
                    if j.status in {JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_PERMANENT}:
                        repo.transition_job(j.job_id, JobStatus.QUEUED, clear_lease=True)
                        retry_count += 1
                fetch_worker_jobs(repo, settings)
            st.success(f"{retry_count} post(s) re-queued for delivery.")
            st.rerun()

    with ctl3:
        if paused > 0:
            if st.button("▶️ Resume Pipeline", use_container_width=True):
                for j in jobs:
                    if j.status is JobStatus.PAUSED:
                        repo.transition_job(j.job_id, JobStatus.QUEUED, clear_lease=True)
                st.success("Pipeline resumed.")
                st.rerun()
        else:
            if st.button("⏸️ Emergency Pause", use_container_width=True, help="Temporarily pause all pending jobs in this pipeline"):
                for j in jobs:
                    if j.status in {JobStatus.QUEUED, JobStatus.APPROVED}:
                        repo.transition_job(j.job_id, JobStatus.PAUSED, clear_lease=True)
                st.warning("Pipeline paused.")
                st.rerun()

    # Filterable Jobs Table
    st.markdown("---")
    st.markdown("### 📋 Scheduled Posts & Delivery Status")

    f_col1, f_col2 = st.columns([2, 2])
    with f_col1:
        status_filter = st.selectbox(
            "Filter by Status",
            options=["All", "QUEUED", "PUBLISHED", "FAILED", "PAUSED"],
            index=0,
        )
    with f_col2:
        platform_filter = st.selectbox(
            "Filter by Platform",
            options=["All", "facebook", "instagram"],
            index=0,
        )

    filtered_jobs = jobs
    if status_filter != "All":
        if status_filter == "FAILED":
            filtered_jobs = [j for j in filtered_jobs if j.status in {JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_PERMANENT}]
        elif status_filter == "QUEUED":
            filtered_jobs = [j for j in filtered_jobs if j.status in {JobStatus.QUEUED, JobStatus.APPROVED, JobStatus.DRAFT}]
        else:
            filtered_jobs = [j for j in filtered_jobs if j.status.value == status_filter]

    if platform_filter != "All":
        filtered_jobs = [j for j in filtered_jobs if j.platform.value == platform_filter]

    if not filtered_jobs:
        st.info("No posts match the selected filters.")
    else:
        table_rows = []
        for j in filtered_jobs:
            status_val = j.status.value
            badge = "✅ Published" if status_val == "PUBLISHED" else ("❌ Failed" if "FAIL" in status_val else f"⏳ {status_val}")
            table_rows.append({
                "Post ID": j.post_id,
                "Platform": j.platform.value.title(),
                "Scheduled At": str(j.scheduled_at),
                "Status": badge,
                "Attempts": j.attempt_count,
                "Remote Post ID": j.remote_post_id or "—",
                "Last Error": (j.last_error_class.value if j.last_error_class else "—") if "FAIL" in status_val else "—",
            })
        st.dataframe(table_rows, use_container_width=True)

    # Expandable Technical Diagnostics
    with st.expander("🔍 Advanced Pipeline Diagnostics & Audit Log"):
        st.caption("Technical execution metadata for system administrators and troubleshooting.")
        st.write(f"**Pipeline ID**: `{active_id}`")
        st.write(f"**Campaign Name**: {campaign.name if campaign else active_id}")
        st.write(f"**Default Timezone**: {campaign.default_timezone if campaign else 'Asia/Kolkata'}")
        st.write(f"**Last Successful Run**: {last_success}")

        if hasattr(repo, "list_audit_events"):
            try:
                audit_events = repo.list_audit_events(limit=10)
                if audit_events:
                    st.markdown("**Recent Audit Trail**:")
                    st.dataframe(
                        [{"Actor": e.actor, "Action": e.action, "Target": e.target, "Time": e.at} for e in audit_events],
                        use_container_width=True,
                    )
            except Exception:
                pass


if __name__ == "__main__":
    render()
