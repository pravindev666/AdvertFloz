"""Connections & Credentials (FR-013, FR-014, PRD §4.10).

Makes the BYOK separation obvious: social accounts (OAuth), installer-owned Meta app,
installer-owned infrastructure, notifications and the AI-provider stance. No secret value is
ever displayed and there is no token-reveal or token-paste control.
"""
from __future__ import annotations

import streamlit as st

from advertfloz.domain.enums import Platform
from advertfloz.ui.components.nav import switch_page
from advertfloz.ui.components.status import chip
from advertfloz.ui.runtime import get_repo, get_settings


def _row(label: str, configured: bool, detail: str) -> None:
    tone = "success" if configured else "warning"
    st.markdown(f"{chip('Configured' if configured else 'Missing', tone)} **{label}** — "
                f'<span class="afz-muted">{detail}</span>', unsafe_allow_html=True)


def render() -> None:
    settings = get_settings()
    repo = get_repo()
    st.markdown('<div class="afz-page-title">Connections &amp; Credentials</div>', unsafe_allow_html=True)

    st.markdown('<div class="afz-section-title">Social accounts</div>', unsafe_allow_html=True)
    st.caption("Connect your own Page and Instagram account through Meta's official OAuth. "
               "No Facebook/Instagram password field and no raw-token paste field exist in AdvertFloz.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Connect Facebook"):
            switch_page(st, "advertfloz/ui/pages/facebook_page.py")
    with c2:
        if st.button("Connect Instagram"):
            switch_page(st, "advertfloz/ui/pages/instagram.py")
    for provider in ("facebook", "instagram"):
        conn = repo.get_connection(Platform(provider))
        if conn is not None:
            st.markdown(
                f"{chip(provider.title(), 'info')} {chip(conn.state.value, 'neutral')} "
                f'<span class="afz-muted">{conn.page_name or conn.account_name or "no target selected"}</span>',
                unsafe_allow_html=True,
            )

    st.markdown('<div class="afz-section-title">Meta Developer App (installer-owned)</div>', unsafe_allow_html=True)
    _row("Meta App ID / Secret", settings.meta_app_configured,
         f"Callback URI must match exactly: {settings.meta_oauth_redirect_uri}")
    if st.button("Test Meta app configuration"):
        if settings.meta_app_configured:
            st.success("App ID and Secret are present in deployment secrets. Live verification requires Phase 0.")
        else:
            st.error("META_APP_ID / META_APP_SECRET are not configured. Set them in deployment secrets, never a form.")

    st.markdown('<div class="afz-section-title">Infrastructure (installer-owned)</div>', unsafe_allow_html=True)
    _row("Cloudflare Worker + service key", settings.worker_configured,
         "Supplied via CLI/provider secret manager; never committed to Git.")
    _row("Token encryption key", settings.token_key_present,
         "Stored separately from the database; required to decrypt OAuth tokens after restore.")
    _row("Public media base URL", bool(settings.media_base_url),
         "Meta must be able to fetch media from this HTTPS base URL for real publishing.")

    st.markdown('<div class="afz-section-title">Notifications</div>', unsafe_allow_html=True)
    _row("Telegram bot + allow-listed chat", settings.telegram_configured,
         "Bot token is a backend secret; chat id is allow-listed and verified with a test message.")

    st.markdown('<div class="afz-section-title">AI provider</div>', unsafe_allow_html=True)
    st.info("No AI API key is required. Prompt creation is local template substitution; campaign production "
            "happens in an external LLM session you operate yourself. AdvertFloz never sends your repository "
            "to any service.")

    st.caption("Credential recovery: see docs/RUNBOOKS/credential_recovery.md. Never share secret values in chat.")


if __name__ == "__main__":
    render()
