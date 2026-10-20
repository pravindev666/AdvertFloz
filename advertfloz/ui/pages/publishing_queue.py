"""Publishing Queue (FR-018..FR-021, PRD §4.7)."""
from __future__ import annotations

import streamlit as st

from advertfloz.domain.enums import JobStatus, Platform
from advertfloz.domain.idempotency import job_key
from advertfloz.infrastructure.persistence.local_sqlite import Repository
from advertfloz.ui.components.tutorial import render_tutorial_callout
from advertfloz.ui.runtime import get_repo, get_settings


def _metrics(repo: Repository) -> dict:
    return repo.count_jobs_by_status()


def render() -> None:
    repo = get_repo()
    st.markdown('<div class="afz-page-title">Publishing Queue</div>', unsafe_allow_html=True)
    render_tutorial_callout("Publishing Queue")

    counts = _metrics(repo)
    if not counts:
        st.info("No jobs yet. Import and activate a campaign to create platform jobs.")
        return

    settings = get_settings()
    campaigns = repo.list_campaigns()
    draft_count = counts.get("DRAFT", 0)
    fb_conn = repo.get_connection(Platform.FACEBOOK)
    target_page_name = fb_conn.page_name if (fb_conn and fb_conn.page_name) else "No target page selected"

    st.markdown('<div class="afz-section-title">🚀 Push Campaign & Schedule to Facebook</div>', unsafe_allow_html=True)
    st.caption(f"Active Target Page: **{target_page_name}**")

    c_push1, c_push2 = st.columns([2, 1])
    if campaigns and draft_count > 0:
        latest_camp = campaigns[-1]
        rev = repo.latest_revision(latest_camp.campaign_id)
        if c_push1.button(f"Queue {draft_count} Posts & Push to Cloudflare Worker", type="primary", use_container_width=True):
            with st.spinner("Uploading images to Cloudflare R2 & syncing schedule to D1..."):
                from advertfloz.infrastructure.worker_client import activate_and_push_campaign
                res = activate_and_push_campaign(repo, settings, latest_camp.campaign_id, rev.revision_id if rev else 1)
                if res.get("ok"):
                    st.success(f"🎉 Successfully queued {res.get('jobs_queued')} jobs & uploaded {res.get('images_uploaded')} images! Scheduled to publish to {target_page_name}.")
                else:
                    st.info(f"Queued {res.get('jobs_queued')} jobs. Sync result: {res.get('sync_response')}")
            st.rerun()
    else:
        c_push1.info(f"All {sum(counts.values())} jobs are already queued or published.")

    if c_push2.button("⚡ Publish Due Post Now", help="Ask Cloudflare Worker to immediately publish any post whose time has arrived", use_container_width=True):
        with st.spinner("Calling Cloudflare Worker tick..."):
            from advertfloz.infrastructure.worker_client import trigger_worker_tick
            tick_res = trigger_worker_tick(settings)
            if tick_res and tick_res.get("ok"):
                r = tick_res.get("result", {})
                st.success(f"Worker tick complete! Published: {r.get('published', 0)}, Claimed: {r.get('claimed', 0)}")
            else:
                st.info(f"Worker response: {tick_res}")
        st.rerun()

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
