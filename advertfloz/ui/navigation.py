"""Application navigation and global frame (PRD §4.1).

Uses ``st.navigation``/``st.Page`` for structured sidebar navigation. Adds the wordmark,
operating mode, scheduler-readiness text, a local-only warning and a discreet connection
summary — without ever exposing token details.
"""
from __future__ import annotations

import streamlit as st

from ..domain.enums import Platform
from .runtime import enforce_hosted_gate, first_run_complete, get_repo, get_settings
from .theme.styles import apply_theme

PAGES = {
    "Overview": "advertfloz/ui/pages/overview.py",
    "Marketing Prompt Builder": "advertfloz/ui/pages/prompt_builder.py",
    "Campaign Import": "advertfloz/ui/pages/campaign_import.py",
    "Calendar": "advertfloz/ui/pages/calendar.py",
    "Image Production": "advertfloz/ui/pages/image_production.py",
    "Publishing Queue": "advertfloz/ui/pages/publishing_queue.py",
    "Facebook Page": "advertfloz/ui/pages/facebook_page.py",
    "Instagram": "advertfloz/ui/pages/instagram.py",
    "Tunnel Helper (Instagram)": "advertfloz/ui/pages/tunnel_helper.py",
    "Connections & Credentials": "advertfloz/ui/pages/connections.py",
    "Reliability & Incidents": "advertfloz/ui/pages/reliability.py",
    "Reports & Export": "advertfloz/ui/pages/reports.py",
    "Settings & Recovery": "advertfloz/ui/pages/settings.py",
}
WIZARD = "advertfloz/ui/pages/first_run_wizard.py"


def _sidebar_frame() -> None:
    settings = get_settings()
    repo = get_repo()
    with st.sidebar:
        st.markdown('<div class="afz-wordmark">◧ AdvertFloz</div>', unsafe_allow_html=True)
        st.caption(f"Mode: {settings.mode.title()}")

        from ..infrastructure.scheduler import heartbeat_stale

        if settings.mode == "local":
            st.caption("Scheduler: local process — stops when this machine sleeps or off.")
        else:
            stale = heartbeat_stale(repo)
            st.caption("Scheduler: remote — " + ("heartbeat stale" if stale else "heartbeat fresh"))

        st.divider()
        fb = repo.get_connection(Platform.FACEBOOK)
        ig = repo.get_connection(Platform.INSTAGRAM)
        if (fb is None or ig is None) and settings.mode == "remote" and settings.worker_configured:
            from ..infrastructure.worker_client import sync_remote_connections
            sync_remote_connections(repo, settings)
            fb = repo.get_connection(Platform.FACEBOOK)
            ig = repo.get_connection(Platform.INSTAGRAM)

        st.caption("Connections")
        fb_desc = f"{fb.state.value} ({fb.page_name})" if (fb and fb.page_name) else (fb.state.value if fb else "not connected")
        ig_desc = f"{ig.state.value} ({ig.account_name})" if (ig and ig.account_name) else (ig.state.value if ig else "not connected")
        st.caption(f"Facebook: {fb_desc}")
        st.caption(f"Instagram: {ig_desc}")

        st.divider()
        if st.session_state.get("afz_authenticated"):
            user_lbl = st.session_state.get("afz_user_email") or "Operator"
            st.caption(f"🔒 Authenticated: {user_lbl}")
            if st.button("Sign Out / Lock", key="afz_signout_btn", use_container_width=True):
                st.session_state["afz_authenticated"] = False
                st.session_state.pop("afz_user_email", None)
                st.rerun()

        st.session_state["afz_dark"] = st.toggle("Dark appearance", value=bool(st.session_state.get("afz_dark", False)))


def run() -> None:
    st.set_page_config(page_title="AdvertFloz", page_icon="◧", layout="wide")
    apply_theme(st, dark=bool(st.session_state.get("afz_dark", False)))

    if not enforce_hosted_gate():
        st.stop()

    st.session_state.setdefault("afz_dark", False)
    _sidebar_frame()

    from .components.notify import local_mode_banner

    local_mode_banner(st, get_settings().mode)

    if not first_run_complete():
        pages = [st.Page(WIZARD, title="First-run setup", icon=":material/rocket_launch:")]
    else:
        pages = [st.Page(path, title=title) for title, path in PAGES.items()]

    navigation = st.navigation({"AdvertFloz": pages})
    navigation.run()
