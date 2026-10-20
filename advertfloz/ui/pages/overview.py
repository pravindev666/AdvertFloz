"""Home – Operational Command Dashboard.

Answers the 5 core operational questions immediately:
1. What campaigns are active?
2. What is scheduled next?
3. What has been published successfully?
4. What has failed or requires attention?
5. Are my integrations and publishing pipelines healthy?
"""
from __future__ import annotations

import streamlit as st

from advertfloz.domain.enums import JobStatus, Platform
from advertfloz.infrastructure.scheduler import heartbeat_stale
from advertfloz.infrastructure.worker_client import fetch_worker_jobs, sync_remote_connections
from advertfloz.ui.components.status import chip
from advertfloz.ui.runtime import get_repo, get_settings


def _cid(c) -> str:
    if hasattr(c, "campaign_id"):
        return str(c.campaign_id)
    if isinstance(c, dict):
        return str(c.get("campaign_id", ""))
    return str(c)


def _cname(c) -> str:
    if hasattr(c, "name"):
        return str(c.name)
    if isinstance(c, dict):
        return str(c.get("name", ""))
    return str(c)


def _ctz(c) -> str:
    if hasattr(c, "default_timezone"):
        return str(c.default_timezone)
    if isinstance(c, dict):
        return str(c.get("default_timezone", "Asia/Kolkata"))
    return "Asia/Kolkata"


def _jid(j) -> str:
    return str(getattr(j, "post_id", j.get("post_id", "") if isinstance(j, dict) else j))


def _jplat(j) -> str:
    p = getattr(j, "platform", j.get("platform", "facebook") if isinstance(j, dict) else "facebook")
    return p.value if hasattr(p, "value") else str(p)


def _jstat(j) -> str:
    s = getattr(j, "status", j.get("status", "QUEUED") if isinstance(j, dict) else "QUEUED")
    return s.value if hasattr(s, "value") else str(s)


def _jsched(j) -> str:
    return str(getattr(j, "scheduled_at", j.get("scheduled_at", "") if isinstance(j, dict) else ""))


def _jtz(j, default_tz: str) -> str:
    return str(getattr(j, "timezone", j.get("timezone", default_tz) if isinstance(j, dict) else default_tz) or default_tz)


def _jcamp(j) -> str:
    return str(getattr(j, "campaign_id", j.get("campaign_id", "") if isinstance(j, dict) else ""))


def _jerr(j) -> str:
    e = getattr(j, "last_error_class", j.get("last_error_class") if isinstance(j, dict) else None)
    if e:
        return e.value if hasattr(e, "value") else str(e)
    return "Execution error"


def render() -> None:
    settings = get_settings()
    repo = get_repo()

    st.markdown('<div class="afz-page-title">📊 Operational Dashboard</div>', unsafe_allow_html=True)
    st.caption("Real-time campaign status, scheduled publications, and integration health.")

    # Auto-sync remote state
    if settings.worker_configured and not st.session_state.get("home_synced"):
        fetch_worker_jobs(repo, settings)
        sync_remote_connections(repo, settings)
        st.session_state["home_synced"] = True

    campaigns = repo.list_campaigns()
    all_jobs = repo.list_jobs()

    # Calculate status aggregates safely
    total_campaigns = len(campaigns)
    if campaigns:
        last_cid = _cid(campaigns[-1])
        rev = repo.latest_revision(last_cid)
        rev_id = rev.revision_id if rev else 1
        total_posts = len(repo.list_posts(last_cid, rev_id))
    else:
        total_posts = 0

    total_jobs = len(all_jobs)

    published_jobs = [j for j in all_jobs if _jstat(j) == "PUBLISHED"]
    queued_jobs = [j for j in all_jobs if _jstat(j) in {"QUEUED", "APPROVED", "DRAFT"}]
    failed_jobs = [j for j in all_jobs if "FAIL" in _jstat(j)]

    # Next scheduled post
    sorted_queued = sorted(queued_jobs, key=lambda j: _jsched(j))
    next_post = sorted_queued[0] if sorted_queued else None

    # Connections
    fb = repo.get_connection(Platform.FACEBOOK)
    ig = repo.get_connection(Platform.INSTAGRAM)
    stale_heartbeat = heartbeat_stale(repo)

    # ═════════════════════════════════════════════════════════════════
    #  QUICK ACTIONS ROW
    # ═════════════════════════════════════════════════════════════════
    qa1, qa2, qa3, qa4 = st.columns([1.5, 1.5, 1.5, 1])
    with qa1:
        if st.button("➕ Create Quick Campaign", type="primary", use_container_width=True):
            st.switch_page("advertfloz/ui/pages/quick_campaign.py")
    with qa2:
        if st.button("⚙️ View Pipelines", use_container_width=True):
            st.switch_page("advertfloz/ui/pages/pipelines.py")
    with qa3:
        if st.button("🛡️ Integration Diagnostics", use_container_width=True):
            st.switch_page("advertfloz/ui/pages/health_diagnostics.py")
    with qa4:
        if st.button("🔄 Refresh", use_container_width=True):
            fetch_worker_jobs(repo, settings)
            st.rerun()

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════
    #  CONNECTED ACCOUNTS & CLOUD INFRASTRUCTURE (Plumbing status)
    # ═════════════════════════════════════════════════════════════════
    st.markdown("#### 🌐 Connected Accounts & Cloud Services")
    st.caption("Live status of your account logins and cloud infrastructure. (These stay connected so you are always ready to post, even when zero campaigns are active).")
    h1, h2, h3, h4 = st.columns(4)

    h1.metric("Cloudflare D1 Database", "Online ✓" if settings.worker_configured else "Local")
    h2.metric("Cloudflare R2 Media", "Ready ✓" if settings.worker_configured else "Local")

    fb_name = getattr(fb, "page_name", None) if fb else None
    fb_lbl = f"✓ {fb_name}" if fb_name else (fb.state.value if fb else "Not Connected")
    h3.metric("Facebook Page", fb_lbl)

    ig_name = getattr(ig, "account_name", None) if ig else None
    ig_lbl = f"✓ @{ig_name}" if ig_name else ("Needs Target" if ig else "Not Connected")
    h4.metric("Instagram Account", ig_lbl)

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════
    #  QUESTIONS 1, 2, 3, 4 IN BALANCED 2x2 OPERATIONAL CARDS
    # ═════════════════════════════════════════════════════════════════
    row1_c1, row1_c2 = st.columns(2)

    # Card 1: What campaigns are active?
    with row1_c1:
        with st.container():
            st.markdown(
                """
                <div class="afz-panel">
                    <div style="font-size:1.1rem; font-weight:600; margin-bottom:8px;">1. Active Campaigns</div>
                """,
                unsafe_allow_html=True,
            )
            if campaigns:
                st.write(f"**{len(campaigns)} active publishing pipeline(s)**")
                for c in campaigns[:4]:
                    st.markdown(f"• **{_cname(c)}** (`{_cid(c)}`) — Timezone: `{_ctz(c)}`")
                if len(campaigns) > 4:
                    st.caption(f"… and {len(campaigns) - 4} more pipelines.")
            else:
                st.info("No active campaigns. Click **Create Quick Campaign** above to begin.")
            st.markdown("</div>", unsafe_allow_html=True)

    # Card 2: What is scheduled next?
    with row1_c2:
        with st.container():
            st.markdown(
                """
                <div class="afz-panel">
                    <div style="font-size:1.1rem; font-weight:600; margin-bottom:8px;">2. Scheduled Next</div>
                """,
                unsafe_allow_html=True,
            )
            active_cids = {str(_cid(c)) for c in campaigns}
            valid_queued = [j for j in sorted_queued if str(_jcamp(j)) in active_cids]
            display_next = valid_queued[0] if valid_queued else (sorted_queued[0] if not campaigns and sorted_queued else None)

            if display_next:
                st.markdown(f"**Post {_jid(display_next)}** on **{_jplat(display_next).title()}**")
                st.write(f"🕒 Due: **{_jsched(display_next)}** ({_jtz(display_next, settings.default_timezone)})")
                st.markdown(f"Pipeline: `{_jcamp(display_next)}` · Status: {chip(_jstat(display_next), 'info')}", unsafe_allow_html=True)
            else:
                st.info("No upcoming posts queued. All scheduled posts have completed!")
            st.markdown("</div>", unsafe_allow_html=True)

    row2_c1, row2_c2 = st.columns(2)

    # Card 3: What has been published successfully?
    with row2_c1:
        with st.container():
            st.markdown(
                """
                <div class="afz-panel">
                    <div style="font-size:1.1rem; font-weight:600; margin-bottom:8px;">3. Published Successfully</div>
                """,
                unsafe_allow_html=True,
            )
            st.metric("Total Posts Published", len(published_jobs))
            if published_jobs:
                st.markdown("**Recent Deliveries**:")
                for pj in published_jobs[-3:]:
                    remote_id = getattr(pj, "remote_post_id", pj.get("remote_post_id") if isinstance(pj, dict) else None)
                    ref = f"Remote ID: {remote_id}" if remote_id else f"Post {_jid(pj)}"
                    up_at = getattr(pj, "updated_at", pj.get("updated_at") if isinstance(pj, dict) else None)
                    st.caption(f"• [{_jplat(pj).title()}] {ref} at {str(up_at)[:19] if up_at else '—'}")
            else:
                st.caption("No published posts recorded yet.")
            st.markdown("</div>", unsafe_allow_html=True)

    # Card 4: What has failed or requires attention?
    with row2_c2:
        with st.container():
            st.markdown(
                """
                <div class="afz-panel">
                    <div style="font-size:1.1rem; font-weight:600; margin-bottom:8px;">4. Attention & Issues</div>
                """,
                unsafe_allow_html=True,
            )
            if failed_jobs:
                st.error(f"⚠️ {len(failed_jobs)} post(s) encountered delivery failures.")
                for fj in failed_jobs[:2]:
                    st.caption(f"• Post {_jid(fj)} ({_jplat(fj)}): {_jerr(fj)}")
                if st.button("Resolve Issues in Pipelines", type="secondary"):
                    st.switch_page("advertfloz/ui/pages/pipelines.py")
            else:
                st.success("✅ Zero active failures. All pipelines and scheduled deliveries are clean.")
            st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    render()
