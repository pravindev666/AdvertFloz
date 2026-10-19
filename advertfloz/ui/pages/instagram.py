"""Instagram panel (FR-012, PRD §4.9). Independent from Facebook."""
from __future__ import annotations

import streamlit as st

from advertfloz.domain.enums import JobStatus, Platform
from advertfloz.infrastructure.meta.policy_registry import get_policy
from advertfloz.infrastructure.security.crypto import TokenCipher
from advertfloz.ui.components.status import chip
from advertfloz.ui.pages import _oauth
from advertfloz.ui.runtime import get_repo, get_settings


def _cipher(settings) -> TokenCipher:
    key = settings.secret("TOKEN_ENCRYPTION_KEY")
    return TokenCipher.single(key, settings.token_encryption_key_id) if key else TokenCipher()


def render() -> None:
    settings = get_settings()
    repo = get_repo()
    platform = Platform.INSTAGRAM
    st.markdown('<div class="afz-page-title">Instagram</div>', unsafe_allow_html=True)

    st.caption(
        "Initial flow: Instagram API with Facebook Login, using an eligible professional Instagram account "
        "linked to your selected Facebook Page. A separate Instagram Login flow is enabled only after "
        "separate documentation and real-account tests."
    )
    for line in _oauth.status_lines(repo, platform):
        st.write(line)

    jobs = repo.list_jobs(platform=platform)
    c1, c2, c3 = st.columns(3)
    c1.metric("Queued", sum(1 for j in jobs if j.status is JobStatus.QUEUED))
    c2.metric("Published", sum(1 for j in jobs if j.status is JobStatus.PUBLISHED))
    c3.metric("Failed", sum(1 for j in jobs if j.status in {JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_PERMANENT}))

    policy = get_policy(platform)
    st.markdown(
        chip(f"policy {policy.version}", "info")
        + chip(f"caption ≤ {policy.max_caption_chars}", "info")
        + chip(f"hashtags ≤ {policy.max_hashtags}", "neutral")
        + chip(f"aspect {policy.min_aspect}–{policy.max_aspect}", "neutral")
        + chip("static single image", "success"),
        unsafe_allow_html=True,
    )

    st.markdown('<div class="afz-section-title">Connect</div>', unsafe_allow_html=True)
    col = st.columns(3)
    if settings.mode == "demo":
        if col[0].button("Connect Instagram (demo)"):
            st.success(_oauth.demo_connect(repo, settings, platform, _cipher(settings)))
            st.rerun()
    else:
        if col[0].button("Connect Instagram"):
            url, message = _oauth.start_oauth(repo, settings, platform)
            if url:
                st.session_state["ig_authorize_url"] = url
                st.info(message)
            else:
                st.error(message)
        if st.session_state.get("ig_authorize_url"):
            st.link_button("Open Meta authorization", st.session_state["ig_authorize_url"])

    if col[1].button("Discover account"):
        st.info("Account discovery runs server-side via the configured Meta flow; the returned username/ID is shown here.")
    if col[2].button("Publish test post"):
        if not st.session_state.get("confirm_ig_test"):
            st.session_state["confirm_ig_test"] = True
            st.warning("Click again to confirm a real Instagram test publish.")
        else:
            repo.audit("operator", "test.post", platform.value, "operator-confirmed IG test post")
            st.success("Instagram test post action recorded.")

    st.markdown('<div class="afz-section-title">Control</div>', unsafe_allow_html=True)
    cu = st.columns(2)
    if cu[0].button("Pause Instagram"):
        repo.pause("instagram", actor="operator")
        st.warning("Instagram paused. Facebook is unaffected.")
    if cu[1].button("Resume Instagram"):
        repo.resume("instagram", actor="operator")
        st.success("Instagram resumed.")

    if st.button("Disconnect Instagram", type="secondary"):
        _oauth.disconnect(repo, platform)
        st.success("Disconnected. Token removed.")

    st.caption("Instagram publishing is not claimed as supported until the real-account flow passes all acceptance tests.")


if __name__ == "__main__":
    render()
