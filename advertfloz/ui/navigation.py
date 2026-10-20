"""Application navigation and global frame.

Implements simplified, intuitive information architecture:
Primary:
  - Home (overview, publishing status, recent activity, warnings)
  - Quick Campaign (guided 5-step wizard)
  - Pipelines (execution progress, safe retries, sync)
  - Facebook (Facebook-specific page switcher, queue, delivery history)
  - Instagram (Instagram-specific eligibility, formats, queue, delivery history)
Secondary:
  - System Health & Integrations (Cloudflare D1, R2, Meta Graph API verification)
  - Calendar (visual timeline)
  - Connections & Credentials
  - Reports & Analytics
  - Settings & Recovery
"""
from __future__ import annotations

import streamlit as st

from ..domain.enums import Platform
from .runtime import enforce_hosted_gate, first_run_complete, get_repo, get_settings
from .theme.styles import apply_theme

PAGES_PRIMARY = {
    "Home": "advertfloz/ui/pages/overview.py",
    "Quick Campaign": "advertfloz/ui/pages/quick_campaign.py",
    "Pipelines": "advertfloz/ui/pages/pipelines.py",
    "Facebook": "advertfloz/ui/pages/facebook_page.py",
    "Instagram": "advertfloz/ui/pages/instagram.py",
}

PAGES_SETTINGS = {
    "Integration Health": "advertfloz/ui/pages/health_diagnostics.py",
    "Calendar": "advertfloz/ui/pages/calendar.py",
    "Connections": "advertfloz/ui/pages/connections.py",
    "Reports & Exports": "advertfloz/ui/pages/reports.py",
    "System Settings": "advertfloz/ui/pages/settings.py",
}

# Backward compatibility alias map
PAGES_LEGACY = {
    "Quick Publish": "advertfloz/ui/pages/quick_campaign.py",
    "Publishing Queue": "advertfloz/ui/pages/pipelines.py",
    "Marketing Prompt Builder": "advertfloz/ui/pages/prompt_builder.py",
    "Campaign Import": "advertfloz/ui/pages/campaign_import.py",
    "Image Production": "advertfloz/ui/pages/image_production.py",
    "Reliability & Incidents": "advertfloz/ui/pages/health_diagnostics.py",
    "Tunnel Helper (Instagram)": "advertfloz/ui/pages/tunnel_helper.py",
    "Overview": "advertfloz/ui/pages/overview.py",
    "Facebook Page": "advertfloz/ui/pages/facebook_page.py",
}

PAGES = {**PAGES_PRIMARY, **PAGES_SETTINGS, **PAGES_LEGACY}
WIZARD = "advertfloz/ui/pages/first_run_wizard.py"


def _sidebar_frame() -> None:
    settings = get_settings()
    repo = get_repo()
    with st.sidebar:
        st.markdown(
            '<div class="afz-wordmark" style="font-size:1.35rem; font-weight:700; margin-bottom:2px;">◈ Campaign Command</div>',
            unsafe_allow_html=True,
        )
        st.caption("Social Media Campaign Platform")

        from ..infrastructure.scheduler import heartbeat_stale

        if settings.mode == "local":
            st.caption("⚡ Mode: Local Desktop Process")
        else:
            stale = heartbeat_stale(repo)
            st.caption("☁️ Mode: Cloudflare Worker (" + ("heartbeat stale" if stale else "heartbeat active") + ")")

        st.divider()

        fb = repo.get_connection(Platform.FACEBOOK)
        ig = repo.get_connection(Platform.INSTAGRAM)
        if (fb is None or ig is None) and settings.mode == "remote" and settings.worker_configured:
            from ..infrastructure.worker_client import sync_remote_connections
            sync_remote_connections(repo, settings)
            fb = repo.get_connection(Platform.FACEBOOK)
            ig = repo.get_connection(Platform.INSTAGRAM)

        st.markdown("**Connected Accounts**")
        fb_desc = f"✓ {fb.page_name}" if (fb and fb.page_name) else (fb.state.value if fb else "Not connected")
        ig_desc = f"✓ @{ig.account_name}" if (ig and ig.account_name) else ("Needs linked account" if ig else "Not connected")
        st.caption(f"📘 Facebook: **{fb_desc}**")
        st.caption(f"📸 Instagram: **{ig_desc}**")

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
    st.set_page_config(page_title="Campaign Command Center", page_icon="◈", layout="wide")
    apply_theme(st, dark=bool(st.session_state.get("afz_dark", False)))

    if not enforce_hosted_gate():
        st.stop()

    st.session_state.setdefault("afz_dark", False)
    _sidebar_frame()

    from .components.notify import local_mode_banner

    local_mode_banner(st, get_settings().mode)

    if not first_run_complete():
        pages = [st.Page(WIZARD, title="First-run setup", icon=":material/rocket_launch:")]
        navigation = st.navigation({"Campaign Manager": pages})
    else:
        primary_pages = [
            st.Page("advertfloz/ui/pages/overview.py", title="Home", icon=":material/home:"),
            st.Page("advertfloz/ui/pages/quick_campaign.py", title="Quick Campaign", icon=":material/bolt:"),
            st.Page("advertfloz/ui/pages/pipelines.py", title="Pipelines", icon=":material/view_timeline:"),
            st.Page("advertfloz/ui/pages/facebook_page.py", title="Facebook", icon=":material/public:"),
            st.Page("advertfloz/ui/pages/instagram.py", title="Instagram", icon=":material/photo_camera:"),
        ]

        settings_pages = [
            st.Page("advertfloz/ui/pages/health_diagnostics.py", title="Integration Health", icon=":material/health_and_safety:"),
            st.Page("advertfloz/ui/pages/calendar.py", title="Calendar", icon=":material/calendar_month:"),
            st.Page("advertfloz/ui/pages/connections.py", title="Connections", icon=":material/key:"),
            st.Page("advertfloz/ui/pages/reports.py", title="Reports & Exports", icon=":material/assessment:"),
            st.Page("advertfloz/ui/pages/settings.py", title="System Settings", icon=":material/settings:"),
        ]

        navigation = st.navigation({
            "Campaign Operations": primary_pages,
            "Settings & Utilities": settings_pages,
        })

    navigation.run()
