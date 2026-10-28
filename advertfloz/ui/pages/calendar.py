"""Calendar + post inspector (FR-009, PRD §4.6). Works with or without a calendar component."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from advertfloz.domain.enums import JobStatus
from advertfloz.domain.utm import build_utm
from advertfloz.ui.components.status import chip, platform_chips, status_badge
from advertfloz.ui.runtime import get_repo, get_settings

try:  # optional, guarded so the app runs without the calendar component
    from streamlit_calendar import calendar as st_calendar

    _CALENDAR_AVAILABLE = True
except Exception:  # pragma: no cover
    _CALENDAR_AVAILABLE = False


def render() -> None:
    settings = get_settings()
    repo = get_repo()
    st.markdown('<div class="afz-page-title">Calendar</div>', unsafe_allow_html=True)

    campaigns = repo.list_campaigns()
    if not campaigns:
        st.info("No campaign imported yet. Start in Campaign Import.")
        return
    campaign = st.selectbox("Campaign", campaigns, format_func=lambda c: f"{c.name} ({c.campaign_id})")
    revision = repo.latest_revision(campaign.campaign_id)
    if revision is None:
        st.warning("No revision found for this campaign.")
        return

    posts = repo.list_posts(campaign.campaign_id, revision.revision_id)
    platform_filter = st.multiselect("Platform", ["facebook", "instagram"], default=["facebook", "instagram"])
    status_filter = st.multiselect("Status", [s.value for s in JobStatus], default=[])

    view_options = ["Agenda", "Month", "Instagram Grid"]
    if not _CALENDAR_AVAILABLE:
        view_options = ["Agenda", "Instagram Grid", "(calendar unavailable)"]
    view = st.radio("View", view_options, horizontal=True)

    jobs = repo.list_jobs(campaign_id=campaign.campaign_id, revision_id=revision.revision_id)
    jobs_by_post: dict[str, list] = {}
    for job in jobs:
        jobs_by_post.setdefault(job.post_id, []).append(job)

    rows = []
    for post in posts:
        post_jobs = [j for j in jobs_by_post.get(post.post_id, []) if j.platform.value in platform_filter]
        if platform_filter and not post_jobs:
            continue
        if status_filter and not any(j.status.value in status_filter for j in post_jobs):
            continue
        rows.append((post, post_jobs))

    # --- Instagram 3x3 Grid Preview ---
    if view == "Instagram Grid":
        _render_instagram_grid(rows)
    elif view == "Month" and _CALENDAR_AVAILABLE:
        events = [
            {
                "title": f"{post.post_id} · {','.join(p.value for p in post.platforms)}",
                "start": post.scheduled_at,
                "end": post.scheduled_at,
                "resourceId": post.post_id,
            }
            for post, _ in rows
        ]
        st_calendar(events=events, initial_view="dayGridMonth")
    else:
        st.dataframe(
            [
                {
                    "post_id": post.post_id,
                    "scheduled": f"{post.scheduled_at} ({post.timezone})",
                    "platforms": ",".join(p.value for p in post.platforms),
                    "statuses": ", ".join(f"{j.platform.value}:{j.status.value}" for j in post_jobs) or "—",
                    "image": f"{post.image_id}.jpg",
                    "enabled": post.enabled,
                }
                for post, post_jobs in rows
            ],
            width="stretch",
        )

    if not rows:
        st.info("No posts match the current filters.")
        return

    st.markdown('<div class="afz-section-title">Post inspector</div>', unsafe_allow_html=True)
    selected_id = st.selectbox("Post", [post.post_id for post, _ in rows])
    post, post_jobs = next(((p, j) for p, j in rows if p.post_id == selected_id), (None, []))

    st.markdown(
        f'{platform_chips(post.platforms)} <span class="afz-mono">{post.post_id}</span> '
        f'<span class="afz-muted">image {post.image_id}.jpg</span>',
        unsafe_allow_html=True,
    )
    asset = repo.get_asset(post.image_id)
    media = Path("data/media") / f"{post.image_id}.jpg"
    if media.exists():
        st.image(str(media), width=220)
    if asset:
        st.caption(f"sha256 {asset.sha256} · {asset.production_state.value} · approved={asset.approved} · sync={asset.sync_state.value}")

    c1, c2 = st.columns(2)
    with c1:
        st.text_input("Facebook caption", post.facebook_caption or post.caption, disabled=True)
        st.text_input("Scheduled (local)", f"{post.scheduled_at} ({post.timezone})", disabled=True)
        st.text_input("Alt text", post.alt_text, disabled=True)
        st.text_input("AI disclosure", post.ai_disclosure_status.value, disabled=True)
    with c2:
        st.text_input("Instagram caption", post.instagram_caption or post.caption, disabled=True)
        st.text_input("Destination URL", post.destination_url, disabled=True)
        if post.destination_url.startswith("https://") and post.campaign_tag:
            try:
                st.text_input("UTM URL", build_utm(post.destination_url, post.campaign_tag, post.post_id), disabled=True)
            except ValueError:
                pass
        st.text_input("Grace minutes", str(post.grace_minutes if post.grace_minutes is not None else ""), disabled=True)

    # --- 125-character first-fold hook indicator ---
    caption_text = post.instagram_caption or post.caption or ""
    if caption_text:
        _render_hook_indicator(caption_text)

    st.markdown("**Per-platform status**")
    for job in post_jobs:
        st.markdown(f"{chip(job.platform.label, 'info')} {status_badge(job.status.value)} "
                    f'<span class="afz-muted">attempts {job.attempt_count} · remote {job.remote_post_id or "—"}</span>',
                    unsafe_allow_html=True)
        if job.permalink:
            st.markdown(f'<a href="{job.permalink}" target="_blank" rel="noopener noreferrer">permalink</a>', unsafe_allow_html=True)

    if any(job.status.is_published for job in post_jobs):
        st.info("This post is published. Its payload is read-only; annotations only.")

    with st.expander("Attempt timeline"):
        for job in post_jobs:
            for attempt in repo.list_attempts(job.job_id):
                st.write(f"{attempt.attempted_at} · {job.platform.value} · {attempt.stage} · "
                         f"{attempt.error_class.value} · {attempt.response_summary}")

    if post.enabled and any(j.status is JobStatus.QUEUED for j in post_jobs):
        st.warning("This post is queued. Editing a claimed/in-flight job requires reconciliation first.")
    else:
        _edit_controls(repo, campaign.campaign_id, revision.revision_id, post, settings)


def _render_instagram_grid(rows) -> None:
    """Render a 3-column Instagram-style profile grid preview."""
    st.markdown('<div class="afz-section-title">📱 Instagram Feed Grid Preview</div>', unsafe_allow_html=True)
    st.caption(
        "Preview how your upcoming posts will appear on an Instagram profile grid. "
        "Check for visual balance — avoid placing two very similar or clashing images side by side."
    )

    # Filter to Instagram posts only
    ig_rows = [
        (post, jobs) for post, jobs in rows
        if any(p.value == "instagram" for p in post.platforms)
    ]

    if not ig_rows:
        st.info("No Instagram posts match the current filters.")
        return

    # How many rows of 3 to show
    grid_size = st.select_slider(
        "Grid rows to preview",
        options=[1, 2, 3, 4, 5],
        value=3,
        help="Each row shows 3 posts (like Instagram's profile grid).",
    )
    max_posts = grid_size * 3

    # Render the grid
    shown = 0
    for row_start in range(0, min(len(ig_rows), max_posts), 3):
        batch = ig_rows[row_start:row_start + 3]
        cols = st.columns(3)
        for idx, (post, _) in enumerate(batch):
            with cols[idx]:
                media = Path("data/media") / f"{post.image_id}.jpg"
                if media.exists():
                    st.image(str(media), width="stretch")
                else:
                    # Placeholder for missing image
                    st.markdown(
                        f'<div style="background:#1a1a2e;border:2px dashed #444;border-radius:8px;'
                        f'height:140px;display:flex;align-items:center;justify-content:center;'
                        f'color:#888;font-size:12px;">{post.image_id}.jpg<br>not found</div>',
                        unsafe_allow_html=True,
                    )
                st.caption(f"{post.post_id} · {post.scheduled_at[:10] if post.scheduled_at else '—'}")
            shown += 1

    st.caption(f"Showing {shown} of {len(ig_rows)} Instagram posts.")


def _render_hook_indicator(caption: str) -> None:
    """Show the 125-character mobile first-fold hook indicator."""
    FOLD_LIMIT = 125
    hook = caption[:FOLD_LIMIT]
    remainder = caption[FOLD_LIMIT:]

    st.markdown('<div class="afz-section-title">📱 125-Character First-Fold Hook</div>', unsafe_allow_html=True)

    if len(caption) <= FOLD_LIMIT:
        st.success(f"✅ Entire caption is within the fold ({len(caption)} chars). Users see everything.")
    else:
        st.markdown(
            f'<div style="padding:8px 12px;border-radius:8px;background:rgba(0,200,100,0.1);border-left:3px solid #00c864;">'
            f'<span style="color:#00c864;font-weight:600;">Visible before "... more" ({len(hook)} chars):</span><br>'
            f'<span style="color:#e0e0e0;">{hook}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="padding:8px 12px;border-radius:8px;background:rgba(255,165,0,0.08);border-left:3px solid #ffa500;margin-top:4px;">'
            f'<span style="color:#ffa500;font-weight:600;">Hidden behind "... more" ({len(remainder)} chars):</span><br>'
            f'<span style="color:#888;">{remainder[:200]}{"..." if len(remainder) > 200 else ""}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Quick quality check on the hook
    weak_starts = ["hi ", "hello ", "hey ", "good morning", "today ", "this is ", "we are "]
    hook_lower = hook.lower().strip()
    if any(hook_lower.startswith(w) for w in weak_starts):
        st.warning("⚠️ The hook starts with a weak greeting. Consider leading with a benefit, question, or bold statement.")
    elif hook.strip().startswith("#"):
        st.warning("⚠️ The hook starts with a hashtag. Move hashtags to the end — lead with your message.")


def _edit_controls(repo, campaign_id, revision_id, post, settings) -> None:
    with st.expander("Edit future post / reschedule"):
        new_dt = st.text_input("New local time (YYYY-MM-DDTHH:MM:SS)", value=post.scheduled_at, key=f"resched-{post.post_id}")
        if st.button("Reschedule", key=f"resched-btn-{post.post_id}"):
            collisions = [
                j for j in repo.list_jobs(campaign_id=campaign_id, revision_id=revision_id)
                if j.post_id != post.post_id and j.scheduled_at == new_dt
            ]
            if collisions:
                st.error("Same-platform schedule collision at that time; choose another slot.")
            elif st.session_state.get(f"confirm-{post.post_id}"):
                repo.update_post_schedule(campaign_id, revision_id, post.post_id, new_dt, post.timezone)
                repo.audit("operator", "post.reschedule", post.post_id, f"{post.scheduled_at} -> {new_dt}")
                st.success("Rescheduled. The change was audited.")
            else:
                st.session_state[f"confirm-{post.post_id}"] = True
                st.warning(f"Confirm reschedule to {new_dt} ({post.timezone}). Click Reschedule again to confirm.")


if __name__ == "__main__":
    render()

