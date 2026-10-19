"""Overview (FR-032, PRD §4.2): answers 'can publishing happen right now?' plus key health."""
from __future__ import annotations

import streamlit as st

from advertfloz.application.services.health import build_overview
from advertfloz.ui.components.nav import page_link
from advertfloz.ui.components.notify import local_mode_banner, notification_area
from advertfloz.ui.components.summary import SummaryItem, summary_strip
from advertfloz.ui.runtime import get_repo, get_settings


def render() -> None:
    settings = get_settings()
    repo = get_repo()
    st.markdown('<div class="afz-page-title">Overview</div>', unsafe_allow_html=True)
    local_mode_banner(st, settings.mode)

    ov = build_overview(repo, mode=settings.mode)

    if not ov.has_data:
        st.info(
            "No campaign yet. Start with the **Marketing Prompt Builder** to create the external-AI prompt, "
            "then import `campaign_plan.csv` and your image ZIP parts in **Campaign Import**."
        )
        page_link(st, "advertfloz/ui/pages/prompt_builder.py", "Open Marketing Prompt Builder")
        return

    tone = "success" if ov.can_publish else "warning"
    items = [
        SummaryItem("Can publish now", "Yes" if ov.can_publish else "No", tone if ov.can_publish else "warning"),
        SummaryItem("Next post", f"{ov.next_post_id} · {ov.next_post_local}" if ov.next_post_id else "none due",
                    "info", "advertfloz/ui/pages/calendar.py"),
        SummaryItem("Posts in active window", str(ov.posts_in_window), "info", "advertfloz/ui/pages/publishing_queue.py"),
        SummaryItem("Asset buffer", f"{ov.buffer_days} day(s)", ov.buffer_status, "advertfloz/ui/pages/image_production.py"),
        SummaryItem("Facebook", ov.facebook_state, "info", "advertfloz/ui/pages/facebook_page.py"),
        SummaryItem("Instagram", ov.instagram_state, "info", "advertfloz/ui/pages/instagram.py"),
        SummaryItem(
            "Heartbeat",
            f"{ov.heartbeat_age_minutes} min ago" if ov.heartbeat_age_minutes is not None else "never",
            "success" if ov.heartbeat_ok else "warning",
            "advertfloz/ui/pages/reliability.py",
        ),
        SummaryItem("Open incidents / UNKNOWN", f"{ov.open_incidents} / {ov.unknown_outcomes}",
                    "danger" if ov.unknown_outcomes else "neutral", "advertfloz/ui/pages/reliability.py"),
        SummaryItem("Latest backup", ov.latest_backup_at or "none", "neutral", "advertfloz/ui/pages/settings.py"),
        SummaryItem("Last restore drill", ov.last_restore_drill_at or "never", "neutral", "advertfloz/ui/pages/settings.py"),
    ]
    summary_strip(st, items, columns=3)
    st.caption(ov.can_publish_reason)

    if ov.token_warnings:
        for warning in ov.token_warnings:
            st.warning(warning)

    notification_area(st, repo, settings.mode)


if __name__ == "__main__":
    render()
