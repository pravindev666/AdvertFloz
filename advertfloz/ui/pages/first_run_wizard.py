"""First-run wizard A–F (PRD §4.11)."""
from __future__ import annotations

import streamlit as st

from advertfloz.domain.enums import Platform
from advertfloz.infrastructure.security.crypto import TokenCipher
from advertfloz.ui.components.nav import switch_page
from advertfloz.ui.components.status import chip
from advertfloz.ui.pages import _oauth
from advertfloz.ui.runtime import get_repo, get_settings, mark_first_run_complete


def _cipher(settings) -> TokenCipher:
    key = settings.secret("TOKEN_ENCRYPTION_KEY")
    return TokenCipher.single(key, settings.token_encryption_key_id) if key else TokenCipher()


def render() -> None:
    settings = get_settings()
    repo = get_repo()
    st.markdown('<div class="afz-page-title">First-run setup</div>', unsafe_allow_html=True)

    step = st.radio("Step", ["A · Mode", "B · Meta App", "C · Facebook", "D · Instagram", "E · Notifications", "F · Readiness"],
                    horizontal=True)

    if step.endswith("Mode"):
        st.write("**Local laptop** — simplest for the 30-post pilot. Local scheduling stops when the laptop or process stops.")
        st.write("**Remote unattended** — requires a separately configured scheduler, database, media storage, alerts and a tested restore.")
        st.warning("Remote mode stays disabled until billing/quotas, durable sync, media retrieval, remote alerts, "
                   "authentication, backup/restore and the laptop-off canary pass.")
    elif step.endswith("Meta App"):
        configured = settings.meta_app_configured
        st.markdown(chip("Configured" if configured else "Missing", "success" if configured else "warning")
                    + ' <span class="afz-muted">The installation operator sets Meta App ID/Secret in deployment secrets.</span>',
                    unsafe_allow_html=True)
        st.code(settings.meta_oauth_redirect_uri, language="text")
        st.caption("This callback URI must match the Meta Developer settings exactly. The App Secret is never entered in a form.")
    elif step.endswith("Facebook"):
        st.write("Connect Facebook, select a Page from the returned list, then run a test connection and a confirmed test post.")
        if settings.mode == "demo":
            if st.button("Connect Facebook (demo)"):
                st.success(_oauth.demo_connect(repo, settings, Platform.FACEBOOK, _cipher(settings)))
        else:
            url, message = _oauth.start_oauth(repo, settings, Platform.FACEBOOK)
            if url:
                st.link_button("Open Meta authorization", url)
            else:
                st.error(message)
    elif step.endswith("Instagram"):
        st.write("Connect Instagram separately. The initial path requires an eligible professional Instagram account "
                 "linked to the selected Page. If none is discovered, Instagram stays disabled.")
        if settings.mode == "demo":
            if st.button("Connect Instagram (demo)"):
                st.success(_oauth.demo_connect(repo, settings, Platform.INSTAGRAM, _cipher(settings)))
        else:
            url, message = _oauth.start_oauth(repo, settings, Platform.INSTAGRAM)
            if url:
                st.link_button("Open Meta authorization", url)
            else:
                st.error(message)
    elif step.endswith("Notifications"):
        st.write("Optional Telegram alerting. The bot token is a backend secret; the chat id is allow-listed.")
        if st.button("Send test alert"):
            from advertfloz.application.services.notifications import send_test_alert
            from advertfloz.infrastructure.notifications.telegram import TelegramBot, TelegramConfig

            bot = TelegramBot(TelegramConfig(settings.secret("TELEGRAM_BOT_TOKEN"), settings.telegram_allowed_chat_id,
                                             settings.secret("TELEGRAM_WEBHOOK_SECRET")))
            sent, detail = send_test_alert(repo, bot)
            (st.success if sent else st.error)(f"Test alert sent={sent} ({detail})")
    else:
        st.write("Per-platform readiness is independent.")
        for platform in (Platform.FACEBOOK, Platform.INSTAGRAM):
            conn = repo.get_connection(platform)
            state = conn.activation_state.value if conn else "Not configured"
            st.markdown(f"{chip(platform.label, 'info')} {chip(state, 'neutral')}", unsafe_allow_html=True)
        if st.button("Finish setup", type="primary"):
            mark_first_run_complete()
            st.success("Setup marked complete. Opening Overview.")
            switch_page(st, "advertfloz/ui/pages/overview.py")


if __name__ == "__main__":
    render()
