"""Facebook – Platform Operations, Page Selection, Queue & History.

Provides Facebook-specific account status, live Page switcher, publishing queue,
and delivery history without cross-contaminating Instagram controls.
"""
from __future__ import annotations

import streamlit as st

from advertfloz.domain.enums import JobStatus, Platform
from advertfloz.infrastructure.worker_client import (
    fetch_worker_jobs,
    sync_meta_pages,
    sync_remote_connections,
)
from advertfloz.ui.components.status import chip
from advertfloz.ui.runtime import get_repo, get_settings


def render() -> None:
    settings = get_settings()
    repo = get_repo()
    platform = Platform.FACEBOOK

    st.markdown('<div class="afz-page-title">📘 Facebook Operations</div>', unsafe_allow_html=True)
    st.caption("Manage Facebook Page connection, target page selection, scheduled queue, and delivery history.")

    # Auto-sync remote state if needed
    if settings.worker_configured and not st.session_state.get("fb_jobs_synced"):
        fetch_worker_jobs(repo, settings)
        sync_remote_connections(repo, settings)
        st.session_state["fb_jobs_synced"] = True

    conn = repo.get_connection(platform)

    # ═════════════════════════════════════════════════════════════════
    #  TARGET FACEBOOK PAGE SELECTOR
    # ═════════════════════════════════════════════════════════════════
    if conn and "fb_available_pages" not in st.session_state and settings.worker_configured:
        res = sync_meta_pages(repo, settings)
        if res and res.get("pages"):
            st.session_state["fb_available_pages"] = res["pages"]

    available_pages = st.session_state.get("fb_available_pages", [])
    if not available_pages and conn and conn.page_id:
        available_pages = [{"id": conn.page_id, "name": conn.page_name or conn.page_id}]

    col_target, col_actions = st.columns([2.5, 1.5])
    with col_target:
        if available_pages:
            current_idx = 0
            for idx, p in enumerate(available_pages):
                if conn and p["id"] == conn.page_id:
                    current_idx = idx
                    break

            selected_page = st.selectbox(
                "Active Facebook Page",
                options=available_pages,
                index=current_idx,
                format_func=lambda p: f"📄 {p.get('name')} (ID: {p.get('id')})",
                key="fb_page_switch_dropdown",
            )

            if selected_page and conn and selected_page["id"] != conn.page_id:
                if st.button(f"Switch Target Page to {selected_page.get('name')}", type="primary"):
                    with st.spinner(f"Updating active page to {selected_page.get('name')}…"):
                        sync_meta_pages(repo, settings, page_id=selected_page["id"])
                    st.success(f"Active target is now **{selected_page.get('name')}**!")
                    st.rerun()
            else:
                st.info(f"Currently targeting: **{conn.page_name or conn.page_id}**")
        else:
            st.warning("No Facebook Page connected yet.")

    with col_actions:
        st.write("")
        st.write("")
        oauth_start_url = f"{settings.worker_base_url.rstrip('/')}/oauth/meta/start" if settings.worker_configured else "#"
        st.link_button("🔗 Reconnect / Switch Meta Account", oauth_start_url, width="stretch")

        if st.button("🔄 Sync Pages from Meta", width="stretch"):
            with st.spinner("Fetching pages from Meta…"):
                res = sync_meta_pages(repo, settings)
                if res and res.get("pages"):
                    st.session_state["fb_available_pages"] = res["pages"]
            st.success("Synced.")
            st.rerun()

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════
    #  METRICS
    # ═════════════════════════════════════════════════════════════════
    jobs = repo.list_jobs(platform=platform)
    queued = sum(1 for j in jobs if j.status in {JobStatus.QUEUED, JobStatus.APPROVED, JobStatus.DRAFT})
    published = sum(1 for j in jobs if j.status is JobStatus.PUBLISHED)
    failed = sum(1 for j in jobs if j.status in {JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_PERMANENT})

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Connection Status", "Connected ✓" if conn and conn.page_id else "Not Connected")
    m2.metric("Queued for Facebook", queued)
    m3.metric("Published to Facebook", published)
    m4.metric("Failed Runs", failed)

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════
    #  FACEBOOK QUEUE & DELIVERY HISTORY
    # ═════════════════════════════════════════════════════════════════
    st.markdown("### 📋 Facebook Publishing Queue & History")

    if not jobs:
        st.info("No Facebook jobs scheduled. Push a campaign in **Quick Campaign** to begin.")
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
                "Last Updated": str(j.updated_at)[:19] if j.updated_at else "—",
            })
        st.dataframe(table_rows, width="stretch")

    # Permissions summary
    with st.expander("ℹ️ Facebook Permissions & Scopes"):
        st.write("**Required Meta Scopes**:")
        st.write("• `pages_show_list` — Discover Pages managed by the operator")
        st.write("• `pages_read_engagement` — Verify page activity and reach")
        st.write("• `pages_manage_posts` — Publish scheduled posts and photos on behalf of the Page")
        st.write(f"**Current Page ID**: `{conn.page_id if conn else 'None'}`")


if __name__ == "__main__":
    render()
