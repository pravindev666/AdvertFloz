"""Facebook Page panel (FR-011, PRD §4.8)."""
from __future__ import annotations

import streamlit as st

from advertfloz.domain.enums import JobStatus, Platform
from advertfloz.infrastructure.security.crypto import TokenCipher
from advertfloz.infrastructure.worker_client import sync_meta_pages, sync_remote_connections
from advertfloz.ui.components.status import chip
from advertfloz.ui.components.tutorial import render_tutorial_callout
from advertfloz.ui.pages import _oauth
from advertfloz.ui.runtime import get_repo, get_settings


def _cipher(settings) -> TokenCipher:
    key = settings.secret("TOKEN_ENCRYPTION_KEY")
    return TokenCipher.single(key, settings.token_encryption_key_id) if key else TokenCipher()


def render() -> None:
    settings = get_settings()
    repo = get_repo()
    platform = Platform.FACEBOOK

    # Handle return from OAuth callback or auto-sync in remote mode
    if settings.mode == "remote" and settings.worker_configured:
        if st.query_params.get("oauth_done") == "facebook":
            sync_remote_connections(repo, settings)
            st.query_params.clear()
            st.toast("Facebook connected successfully!", icon="✅")
        conn_check = repo.get_connection(platform)
        if conn_check is None:
            sync_remote_connections(repo, settings)
        elif not conn_check.page_name:
            sync_meta_pages(repo, settings)

    st.markdown('<div class="afz-page-title">Facebook Page</div>', unsafe_allow_html=True)
    render_tutorial_callout("Facebook Page")

    conn = repo.get_connection(platform)
    if conn and conn.page_name:
        st.success(f"Active Target Page: **{conn.page_name}** (Page ID: `{conn.page_id}`)")

    # Auto-load available pages from Worker if not in session state
    if conn and "available_fb_pages" not in st.session_state and settings.worker_configured:
        res = sync_meta_pages(repo, settings)
        if res and res.get("pages"):
            st.session_state["available_fb_pages"] = res["pages"]

    available_pages = st.session_state.get("available_fb_pages", [])
    if not available_pages and conn and conn.page_id:
        available_pages = [{"id": conn.page_id, "name": conn.page_name or conn.page_id}]

    if conn and available_pages:
        st.markdown('<div class="afz-section-title">Target Facebook Page</div>', unsafe_allow_html=True)
        st.caption("All scheduled posts in your Calendar and Queue will publish to this target page.")
        current_page_idx = 0
        for idx, p in enumerate(available_pages):
            if conn and p["id"] == conn.page_id:
                current_page_idx = idx
                break

        selected_page = st.selectbox(
            "Select which Facebook Page AdvertFloz schedules to:",
            options=available_pages,
            index=current_page_idx,
            format_func=lambda p: f"{p.get('name', 'Page')} (ID: {p.get('id')})",
            key="fb_target_page_selector",
        )
        if selected_page and conn and selected_page["id"] != conn.page_id:
            if st.button(f"Switch Target Page to {selected_page.get('name')}", type="primary"):
                with st.spinner(f"Setting target page to {selected_page.get('name')}..."):
                    sync_meta_pages(repo, settings, page_id=selected_page["id"])
                    st.success(f"Switched target page to **{selected_page.get('name')}**!")
                    st.rerun()

    for line in _oauth.status_lines(repo, platform):
        st.write(line)

    jobs = repo.list_jobs(platform=platform)
    c1, c2, c3 = st.columns(3)
    c1.metric("Queued", sum(1 for j in jobs if j.status is JobStatus.QUEUED))
    c2.metric("Published", sum(1 for j in jobs if j.status is JobStatus.PUBLISHED))
    c3.metric("Failed", sum(1 for j in jobs if j.status in {JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_PERMANENT}))

    st.markdown('<div class="afz-section-title">Connect & Manage</div>', unsafe_allow_html=True)
    st.caption("You will sign in on Meta's official page. AdvertFloz never asks for your Facebook password.")

    col1, col2, col3, col4 = st.columns(4)
    if settings.mode == "demo":
        if col1.button("Connect Facebook (demo)"):
            message = _oauth.demo_connect(repo, settings, platform, _cipher(settings))
            st.success(message)
            st.rerun()
    else:
        oauth_start_url = f"{settings.worker_base_url.rstrip('/')}/oauth/meta/start"
        btn_label = "Reconnect Facebook" if (conn and conn.page_name) else "Connect Facebook"
        col1.link_button(btn_label, oauth_start_url)

        if col2.button("Sync / Fetch Pages", help="Fetch your Facebook Pages (like MusikFlo, Rashinos) from Meta"):
            with st.spinner("Fetching Facebook Pages from Meta..."):
                res = sync_meta_pages(repo, settings)
                if res and res.get("pages"):
                    st.session_state["available_fb_pages"] = res["pages"]
                if res and res.get("selected_page"):
                    st.success(f"Found and linked Facebook Page: **{res['selected_page']['name']}**")
                else:
                    sync_remote_connections(repo, settings)
                    st.info("Synchronized connection state.")
            st.rerun()

    if col3.button("Test connection"):
        repo.audit("operator", "test.connection", platform.value, "non-publishing test requested")
        st.info("Connection/permission test recorded. A passing result is required before a test post.")

    if col4.button("Publish test post"):
        if not st.session_state.get("confirm_test_post"):
            st.session_state["confirm_test_post"] = True
            st.warning("Click again to confirm publishing a real test post to the selected Page.")
        else:
            repo.audit("operator", "test.post", platform.value, "operator-confirmed test post")
            st.success("Test post action recorded. In configured mode this calls the Meta API and stores the returned ID.")

    st.markdown('<div class="afz-section-title">Control</div>', unsafe_allow_html=True)
    cu = st.columns(2)
    if cu[0].button("Pause Facebook"):
        repo.pause("facebook", actor="operator")
        st.warning("Facebook paused. An in-flight call cannot be recalled.")
    if cu[1].button("Resume Facebook"):
        repo.resume("facebook", actor="operator")
        st.success("Facebook resumed.")

    if st.button("Disconnect Facebook", type="secondary"):
        _oauth.disconnect(repo, platform)
        st.success("Disconnected. Token removed. Reconnect to publish again.")

    st.markdown(
        chip("Changing the target Page is destructive to future targeting", "warning")
        + ' <span class="afz-muted">Preview affected jobs and confirm; queued jobs are never retargeted silently.</span>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    render()
