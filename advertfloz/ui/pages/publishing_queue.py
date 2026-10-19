"""Publishing Queue (FR-018..FR-021, PRD §4.7)."""
from __future__ import annotations

import streamlit as st

from advertfloz.domain.enums import JobStatus, Platform
from advertfloz.domain.idempotency import job_key
from advertfloz.infrastructure.persistence.local_sqlite import Repository
from advertfloz.ui.runtime import get_repo


def _metrics(repo: Repository) -> dict:
    return repo.count_jobs_by_status()


def render() -> None:
    repo = get_repo()
    st.markdown('<div class="afz-page-title">Publishing Queue</div>', unsafe_allow_html=True)

    counts = _metrics(repo)
    if not counts:
        st.info("No jobs yet. Import and activate a campaign to create platform jobs.")
        return

    cols = st.columns(4)
    for index, key in enumerate(
        ["QUEUED", "PUBLISHED", "FAILED_RETRYABLE", "UNKNOWN_OUTCOME"]
    ):
        cols[index].metric(key.replace("_", " ").title(), counts.get(key, 0))

    emergency = st.columns([1, 1, 2])
    if emergency[0].button("Emergency pause (all)", type="primary"):
        repo.pause("all", actor="operator")
        st.warning("All dispatch paused durably. An already in-flight provider call cannot be recalled.")
    if emergency[1].button("Resume all"):
        repo.resume("all", actor="operator")
        st.success("Dispatch resumed.")

    status_filter = st.multiselect("Status", [s.value for s in JobStatus], default=[])
    platform_filter = st.multiselect("Platform", ["facebook", "instagram"], default=[])

    jobs = repo.list_jobs(
        statuses=[JobStatus(s) for s in status_filter] if status_filter else None,
        platform=Platform(platform_filter[0]) if len(platform_filter) == 1 else None,
    )
    if platform_filter:
        jobs = [j for j in jobs if j.platform.value in platform_filter]

    if not jobs:
        st.info("No jobs match the filters.")
        return

    st.dataframe(
        [
            {
                "job_id": j.job_id,
                "post_id": j.post_id,
                "platform": j.platform.value,
                "status": j.status.value,
                "scheduled": j.scheduled_at,
                "attempts": j.attempt_count,
                "next_retry": j.next_retry_at,
                "error": j.last_error_class.value,
                "remote_id": j.remote_post_id,
                "idempotency": j.idempotency_key,
            }
            for j in jobs
        ],
        width="stretch",
    )

    st.markdown('<div class="afz-section-title">Row actions</div>', unsafe_allow_html=True)
    options = {f"#{j.job_id} {j.post_id} · {j.platform.value} · {j.status.value}": j for j in jobs}
    chosen = st.selectbox("Job", list(options))
    job = options[chosen]

    c1, c2, c3 = st.columns(3)
    if c1.button("Retry (retryable only)", disabled=not job.status.allows_manual_retry):
        repo.transition_job(job.job_id, JobStatus.QUEUED, clear_lease=True)
        repo.audit("operator", "job.retry", f"{job.post_id}:{job.platform.value}", "manual retry")
        st.success("Job requeued for retry.")
        st.rerun()
    if job.status.requires_reconciliation:
        c2.warning("UNKNOWN_OUTCOME must be reconciled with the provider before any retry.")
    if c3.button(f"Pause {job.platform.value}"):
        repo.pause(job.platform.value, actor="operator")
        st.warning(f"{job.platform.value} paused.")
    if st.button(f"Resume {job.platform.value}"):
        repo.resume(job.platform.value, actor="operator")
        st.success(f"{job.platform.value} resumed.")

    st.caption(f"Idempotency key: {job_key(job.campaign_id, job.revision_id, job.post_id, job.platform)}")


if __name__ == "__main__":
    render()
