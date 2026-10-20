"""Facebook Page panel (FR-011, PRD §4.8)."""
from __future__ import annotations

import streamlit as st

from advertfloz.domain.enums import JobStatus, Platform
from advertfloz.infrastructure.security.crypto import TokenCipher
from advertfloz.infrastructure.worker_client import sync_meta_pages, sync_remote_connections
from advertfloz.ui.components.status import chip
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

    conn = repo.get_connection(platform)
    if conn and conn.page_name:
        st.success(f"Connected Facebook Page: **{conn.page_name}** (Page ID: `{conn.page_id}`)")

    for line in _oauth.status_lines(repo, platform):
        st.write(line)

    jobs = repo.list_jobs(platform=platform)
    c1, c2, c3 = st.columns(3)
    c1.metric("Queued", sum(1 for j in jobs if j.status is JobStatus.QUEUED))
    c2.metric("Published", sum(1 for j in jobs if j.status is JobStatus.PUBLISHED))
    c3.metric("Failed", sum(1 for j in jobs if j.status in {JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_PERMANENT}))

    st.markdown('<div class="afz-section-title">Connect</div>', unsafe_allow_html=True)
    st.caption("You will sign in on Meta's official page. AdvertFloz never asks for your Facebook password.")

    col = st.columns(4)
    if settings.mode == "demo":
        if col[0].button("Connect Facebook (demo)"):
            message = _oauth.demo_connect(repo, settings, platform, _cipher(settings))
            st.success(message)
            st.rerun()
    else:
        if col[0].button("Connect Facebook"):
            url, message = _oauth.start_oauth(repo, settings, platform)
            if url:
                st.session_state["fb_authorize_url"] = url
                st.info(message)
            else:
                st.error(message)

        if col[1].button("Sync / Fetch Page", help="Fetch your Facebook Pages (like Musicflo) from Meta via Worker"):
            with st.spinner("Fetching Facebook Pages..."):
                res = sync_meta_pages(repo, settings)
                if res and res.get("selected_page"):
                    st.success(f"Found and linked Facebook Page: **{res['selected_page']['name']}**")
                else:
                    sync_remote_connections(repo, settings)
                    st.info("Synchronized connection state.")
            st.rerun()

        if st.session_state.get("fb_authorize_url"):
            st.link_button("Open Meta authorization", st.session_state["fb_authorize_url"])

    if col[1].button("Test connection"):
        repo.audit("operator", "test.connection", platform.value, "non-publishing test requested")
        st.info("Connection/permission test recorded. A passing result is required before a test post.")

    if col[2].button("Publish test post"):
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
