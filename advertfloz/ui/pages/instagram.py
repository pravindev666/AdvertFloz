"""Instagram – Platform Operations, Professional Account Eligibility & Queue.

Provides Instagram-specific account status, media format validation, eligibility verification,
and delivery history completely separated from Facebook controls.
"""
from __future__ import annotations

import streamlit as st

from advertfloz.domain.enums import JobStatus, Platform
from advertfloz.infrastructure.meta.policy_registry import get_policy
from advertfloz.infrastructure.worker_client import (
    call_worker,
    fetch_worker_jobs,
    sync_remote_connections,
)
from advertfloz.ui.components.status import chip
from advertfloz.ui.runtime import get_repo, get_settings


def render() -> None:
    settings = get_settings()
    repo = get_repo()
    platform = Platform.INSTAGRAM

    st.markdown('<div class="afz-page-title">📸 Instagram Operations</div>', unsafe_allow_html=True)
    st.caption("Manage Instagram professional account linkage, content formatting rules, scheduled queue, and delivery history.")

    # Auto-sync
    if settings.worker_configured and not st.session_state.get("ig_jobs_synced"):
        fetch_worker_jobs(repo, settings)
        sync_remote_connections(repo, settings)
        st.session_state["ig_jobs_synced"] = True

    conn = repo.get_connection(platform)

    # ═════════════════════════════════════════════════════════════════
    #  ACCOUNT ELIGIBILITY & LINKAGE STATUS
    # ═════════════════════════════════════════════════════════════════
    st.markdown("### 🔐 Professional Account Linkage & Eligibility")

    col_status, col_oauth = st.columns([2.5, 1.5])
    with col_status:
        has_account = bool(conn and conn.account_name)
        status_chip = chip("Eligible & Connected", "success") if has_account else chip("Needs Linked Account", "warning")
        st.markdown(
            f"""
            <div class="afz-panel">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <b>Instagram Account Status</b>
                    <span>{status_chip}</span>
                </div>
                <div style="font-size:0.95rem; margin-bottom:6px;">
                    {'Active Instagram: <b>@' + conn.account_name + '</b>' if has_account else 'No professional Instagram account linked to your Facebook Page.'}
                </div>
                <div style="font-size:0.85rem; color:var(--afz-text-alt);">
                    Meta requires an Instagram Professional (Business or Creator) account linked to your Facebook Page for API publishing.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_oauth:
        oauth_start_url = f"{settings.worker_base_url.rstrip('/')}/oauth/meta/start" if settings.worker_configured else "#"
        st.link_button("🔗 Connect / Re-authorize Meta", oauth_start_url, use_container_width=True)

        if st.button("🔍 Discover Linked Account", use_container_width=True, help="Scan connected Facebook Pages for linked Instagram accounts"):
            with st.spinner("Checking Meta Graph API for linked Instagram accounts…"):
                res = call_worker(settings, "/api/meta/pages")
                if res and res.get("pages"):
                    st.info(f"Checked {len(res['pages'])} Facebook Pages. Link Instagram in Facebook Page Settings > Linked Accounts.")
                else:
                    st.warning("Could not reach Meta API. Please check your connection.")
            st.rerun()

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════
    #  PUBLISHING FORMAT & SPECIFICATION POLICIES
    # ═════════════════════════════════════════════════════════════════
    st.markdown("### 📐 Instagram Publishing Requirements")
    st.caption("Only formats actively supported by the Meta Graph Content Publishing API are enabled.")

    policy = get_policy(platform)
    c_f1, c_f2, c_f3, c_f4 = st.columns(4)
    c_f1.metric("Supported Media", "Single Image")
    c_f2.metric("Aspect Ratio", f"{policy.min_aspect} – {policy.max_aspect} (1:1 ideal)")
    c_f3.metric("Max Caption", f"{policy.max_caption_chars:,} chars")
    c_f4.metric("Reels / Stories", "Not Enabled")

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════
    #  METRICS
    # ═════════════════════════════════════════════════════════════════
    jobs = repo.list_jobs(platform=platform)
    queued = sum(1 for j in jobs if j.status in {JobStatus.QUEUED, JobStatus.APPROVED, JobStatus.DRAFT})
    published = sum(1 for j in jobs if j.status is JobStatus.PUBLISHED)
    failed = sum(1 for j in jobs if j.status in {JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_PERMANENT})

    m1, m2, m3 = st.columns(3)
    m1.metric("Queued for Instagram", queued)
    m2.metric("Published to Instagram", published)
    m3.metric("Failed Runs", failed)

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════
    #  INSTAGRAM QUEUE & HISTORY
    # ═════════════════════════════════════════════════════════════════
    st.markdown("### 📋 Instagram Publishing Queue & History")

    if not jobs:
        st.info("No Instagram jobs scheduled. To target Instagram, select '📸 Instagram' when launching in **Quick Campaign**.")
    else:
        table_rows = []
        for j in jobs:
            status_val = j.status.value
            badge = "✅ Published" if status_val == "PUBLISHED" else ("❌ Failed" if "FAIL" in status_val else f"⏳ {status_val}")
            table_rows.append({
                "Post ID": j.post_id,
                "Pipeline": j.campaign_id,
                "Scheduled At": str(j.scheduled_at),
                "Status": badge,
                "Remote Post ID": j.remote_post_id or "—",
                "Last Error": (j.last_error_class.value if j.last_error_class else "—") if "FAIL" in status_val else "—",
            })
        st.dataframe(table_rows, use_container_width=True)

    # Emergency Control
    st.markdown("---")
    st.markdown("#### ⏸️ Instagram Platform Controls")
    cu1, cu2 = st.columns(2)
    with cu1:
        if st.button("⏸️ Pause Instagram Deliveries", use_container_width=True):
            repo.pause("instagram", actor="operator")
            st.warning("Instagram publishing paused. Facebook remains unaffected.")
    with cu2:
        if st.button("▶️ Resume Instagram Deliveries", use_container_width=True):
            repo.resume("instagram", actor="operator")
            st.success("Instagram publishing resumed.")


if __name__ == "__main__":
    render()
