"""🚀 Quick Publish – Upload, approve, and push to Facebook in one page.

Combines the essential actions from Campaign Import, Image Production,
Facebook Page, and Publishing Queue into a single streamlined workflow.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from advertfloz.application.services.campaign_import import ImportLimits, assemble_import
from advertfloz.application.services.campaign_revision import commit_import
from advertfloz.domain.enums import JobStatus, Platform, ProductionState
from advertfloz.infrastructure.worker_client import (
    activate_and_push_campaign,
    fetch_worker_jobs,
    force_publish_all_today,
    sync_meta_pages,
    sync_remote_connections,
    trigger_worker_tick,
)
from advertfloz.ui.components.status import chip
from advertfloz.ui.runtime import get_repo, get_settings


# ── helpers ──────────────────────────────────────────────────────────────


def _save_uploads(files_data: list[tuple[str, bytes]]) -> list[Path]:
    """Save uploaded file data to temp directory and return paths."""
    paths: list[Path] = []
    upload_dir = Path(tempfile.mkdtemp(prefix="afz_qp_"))
    for name, data in files_data:
        target = upload_dir / name
        target.write_bytes(data)
        paths.append(target)
    return paths


def _persist_plan():
    """Callback: fires when the plan CSV uploader changes."""
    uploaded = st.session_state.get("qp_plan_csv")
    if uploaded is not None:
        st.session_state["qp_persisted_plan"] = (uploaded.name, uploaded.getvalue())
        # Reset committed flag so re-upload triggers re-validation
        st.session_state["qp_committed"] = False


def _persist_zips():
    """Callback: fires when the ZIP uploader changes."""
    uploaded = st.session_state.get("qp_zip_files")
    if uploaded:
        st.session_state["qp_persisted_zips"] = [(f.name, f.getvalue()) for f in uploaded]
        st.session_state["qp_committed"] = False


# ── main render ──────────────────────────────────────────────────────────


def render() -> None:
    settings = get_settings()
    repo = get_repo()

    st.markdown(
        '<div class="afz-page-title">🚀 Quick Publish</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Upload your campaign CSV and image ZIP, review, pick your "
        "Facebook page, and publish — all in one place."
    )

    # Persistent state across Streamlit reruns
    st.session_state.setdefault("qp_persisted_plan", None)
    st.session_state.setdefault("qp_persisted_zips", [])
    st.session_state.setdefault("qp_committed", False)

    # ═══════════════════════════════════════════════════════════════════
    #  STEP 1 — UPLOAD
    # ═══════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("### 📁  Step 1 · Upload Your Content")
    st.caption(
        "Drop your **campaign_plan.csv** (schedules & captions) and your "
        "**image ZIP** (1.jpg, 2.jpg …) side by side."
    )

    col_csv, col_zip = st.columns(2)
    with col_csv:
        st.file_uploader(
            "📄 Campaign Plan CSV",
            type=["csv"],
            key="qp_plan_csv",
            on_change=_persist_plan,
            help="Your campaign_plan.csv with post schedules, captions, and platforms",
        )
        if st.session_state["qp_persisted_plan"]:
            name, data = st.session_state["qp_persisted_plan"]
            st.success(f"✅ `{name}` ({len(data):,} bytes)")

    with col_zip:
        st.file_uploader(
            "🗂️ Image ZIP Archive",
            type=["zip"],
            accept_multiple_files=True,
            key="qp_zip_files",
            on_change=_persist_zips,
            help="ZIP containing JPEG images (1.jpg, 2.jpg, …)",
        )
        if st.session_state["qp_persisted_zips"]:
            total = sum(len(d) for _, d in st.session_state["qp_persisted_zips"])
            st.success(
                f"✅ {len(st.session_state['qp_persisted_zips'])} "
                f"ZIP(s) ({total // 1024:,} KB)"
            )

    # ── Auto-validate and commit ─────────────────────────────────────
    plan_item = st.session_state.get("qp_persisted_plan")
    zip_items = st.session_state.get("qp_persisted_zips") or []

    campaigns = repo.list_campaigns()
    campaign = campaigns[-1] if campaigns else None

    if plan_item and zip_items and not st.session_state.get("qp_committed"):
        limits = ImportLimits(
            max_image_bytes=settings.max_image_bytes,
            max_expanded_bytes=settings.max_expanded_bytes,
            max_archive_bytes=settings.max_archive_bytes,
        )
        plan_paths = _save_uploads([plan_item])
        zip_paths = _save_uploads(zip_items)

        with st.spinner("Validating campaign…"):
            result = assemble_import(
                campaign_id="campaign-1",
                campaign_name="campaign-1",
                revision_id=1,
                plan_path=plan_paths[0],
                zip_paths=zip_paths,
                limits=limits,
            )

        blocking = [i for i in result.issues if i.is_blocking]
        if blocking:
            st.error(f"❌ {len(blocking)} error(s) — fix your CSV / ZIP and re-upload")
            st.dataframe(
                [{"row": i.row, "field": i.field, "message": i.message} for i in blocking],
                use_container_width=True,
            )
        elif result.ok and result.mapping_complete():
            counts = result.platform_counts()
            st.success(
                f"✅ Valid!  {len(result.posts)} posts · "
                f"{len(result.assets)} images · "
                f"{counts.get('facebook', 0)} FB jobs · "
                f"{counts.get('instagram', 0)} IG jobs"
            )
            if st.button(
                "📥 Import Campaign", type="primary", use_container_width=True
            ):
                with st.spinner("Committing campaign…"):
                    commit_import(repo, result)
                    st.session_state["qp_committed"] = True
                st.success("🎉 Campaign imported!")
                st.rerun()
        else:
            missing = result.missing_image_ids()
            if missing:
                st.warning(f"⚠️ Missing images: {missing[:20]}")

    elif st.session_state.get("qp_committed") or campaign is not None:
        st.success("✅ Campaign is imported and ready.")

    # ═══════════════════════════════════════════════════════════════════
    #  STEP 2 — REVIEW & APPROVE
    # ═══════════════════════════════════════════════════════════════════
    assets = repo.list_assets()
    if assets:
        st.markdown("---")
        st.markdown("### 👁️  Step 2 · Review & Approve Images")

        ready_count = sum(1 for a in assets if a.approved)
        total_count = len(assets)

        st.markdown(
            chip(
                f"{ready_count} approved / {total_count} total",
                "success" if ready_count == total_count else "warning",
            ),
            unsafe_allow_html=True,
        )

        # Approve All
        if ready_count < total_count:
            if st.button(
                "✅ Approve All Images",
                type="primary",
                use_container_width=True,
            ):
                for a in assets:
                    if not a.approved:
                        repo.update_production_state(
                            a.image_id, ProductionState.APPROVED, approved=True,
                        )
                        repo.audit(
                            "operator", "asset.approve",
                            str(a.image_id), "quick-publish bulk approve",
                        )
                st.success(f"All {total_count} images approved!")
                st.rerun()
        else:
            st.success("All images are approved ✓")

        # Image grid (first 12)
        display_count = min(total_count, 12)
        grid_cols = st.columns(min(4, display_count) or 1)
        for idx, asset in enumerate(assets[:display_count]):
            with grid_cols[idx % len(grid_cols)]:
                post_id = f"P{asset.image_id:03d}"
                badge = (
                    chip("✓ approved", "success")
                    if asset.approved
                    else chip("pending", "warning")
                )
                st.markdown(
                    f'<div class="afz-panel">'
                    f'<b class="afz-mono">{asset.image_id}.jpg</b><br>'
                    f'<span class="afz-muted">{post_id}</span><br>'
                    f"{badge}</div>",
                    unsafe_allow_html=True,
                )
                media = Path("data/media") / f"{asset.image_id}.jpg"
                if media.exists():
                    st.image(str(media), width=140)

        if total_count > 12:
            st.caption(
                f"… and {total_count - 12} more. "
                "See all in **Image Production** (sidebar)."
            )

    # ═══════════════════════════════════════════════════════════════════
    #  STEP 3 — TARGET PAGE & PUBLISH
    # ═══════════════════════════════════════════════════════════════════
    # Refresh campaign ref (may have been committed above)
    if campaign is None:
        campaigns = repo.list_campaigns()
        campaign = campaigns[-1] if campaigns else None

    if campaign is None:
        return  # Nothing to publish yet

    st.markdown("---")
    st.markdown("### 🎯  Step 3 · Select Facebook Page & Publish")

    platform = Platform.FACEBOOK

    # ── Sync connections on first load ────────────────────────────────
    if settings.mode == "remote" and settings.worker_configured:
        conn = repo.get_connection(platform)
        if conn is None:
            sync_remote_connections(repo, settings)
            conn = repo.get_connection(platform)

        if conn and "qp_fb_pages" not in st.session_state:
            res = sync_meta_pages(repo, settings)
            if res and res.get("pages"):
                st.session_state["qp_fb_pages"] = res["pages"]

    conn = repo.get_connection(platform)
    available_pages = st.session_state.get("qp_fb_pages", [])
    if not available_pages and conn and conn.page_id:
        available_pages = [
            {"id": conn.page_id, "name": conn.page_name or conn.page_id}
        ]

    # ── Page selector ─────────────────────────────────────────────────
    if conn and available_pages:
        current_idx = 0
        for idx, p in enumerate(available_pages):
            if p["id"] == conn.page_id:
                current_idx = idx
                break

        selected_page = st.selectbox(
            "🎯 Target Facebook Page",
            options=available_pages,
            index=current_idx,
            format_func=lambda p: p.get("name", "Page"),
            key="qp_page_selector",
        )

        if selected_page and selected_page["id"] != conn.page_id:
            if st.button(
                f"Switch to {selected_page.get('name')}", type="secondary"
            ):
                with st.spinner(f"Switching to {selected_page.get('name')}…"):
                    sync_meta_pages(
                        repo, settings, page_id=selected_page["id"]
                    )
                st.rerun()
        else:
            st.info(f"📌 Publishing to **{conn.page_name or conn.page_id}**")

    elif not conn:
        oauth_url = (
            f"{settings.worker_base_url.rstrip('/')}/oauth/meta/start"
            if settings.worker_configured
            else "#"
        )
        st.warning("Facebook is not connected yet.")
        st.link_button("🔗 Connect Facebook", oauth_url)

    # Refresh pages
    if settings.worker_configured:
        if st.button(
            "🔄 Refresh Facebook Pages",
            help="Re-fetch your Facebook Pages from Meta",
        ):
            with st.spinner("Fetching pages…"):
                res = sync_meta_pages(repo, settings)
                if res and res.get("pages"):
                    st.session_state["qp_fb_pages"] = res["pages"]
                    st.success(f"Found {len(res['pages'])} page(s)")
                else:
                    sync_remote_connections(repo, settings)
                    st.info("Synced connection state.")
            st.rerun()

    # ── Status metrics ────────────────────────────────────────────────
    st.markdown("---")

    # Sync latest live job statuses from Cloudflare D1
    if settings.worker_configured and not st.session_state.get("qp_jobs_synced"):
        fetch_worker_jobs(repo, settings)
        st.session_state["qp_jobs_synced"] = True

    jobs = repo.list_jobs(platform=platform)
    draft_count = sum(
        1
        for j in jobs
        if j.status
        in {
            JobStatus.DRAFT,
            JobStatus.APPROVED,
            JobStatus.READY_FOR_REVIEW,
            JobStatus.QUEUED,
        }
    )
    published_count = sum(1 for j in jobs if j.status is JobStatus.PUBLISHED)
    failed_count = sum(
        1
        for j in jobs
        if j.status
        in {JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_PERMANENT}
    )

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("📤 Queued", draft_count)
    mc2.metric("✅ Published", published_count)
    mc3.metric("❌ Failed", failed_count)

    # ── Publish buttons ───────────────────────────────────────────────
    rev = (
        repo.latest_revision(campaign.campaign_id)
        if hasattr(repo, "latest_revision")
        else None
    )

    col_push, col_now, col_force = st.columns([1.2, 1, 1.2])

    with col_push:
        if st.button(
            "🚀 Push to Facebook",
            type="primary",
            use_container_width=True,
            help="Upload images to R2, queue all jobs, and sync schedule",
        ):
            with st.spinner("Uploading images & syncing schedule…"):
                res = activate_and_push_campaign(
                    repo,
                    settings,
                    campaign.campaign_id,
                    rev.revision_id if rev else 1,
                )
                if res.get("ok"):
                    st.success(
                        f"🎉 Pushed! {res.get('images_uploaded')} images "
                        f"uploaded, {res.get('jobs_queued')} jobs queued!"
                    )
                else:
                    st.info(
                        f"Queued {res.get('jobs_queued')} jobs. "
                        f"Sync: {res.get('sync_response')}"
                    )
            st.rerun()

    with col_now:
        if st.button(
            "⚡ Publish Due Now",
            use_container_width=True,
            help="Immediately publish any posts whose scheduled time has arrived",
        ):
            with st.spinner("Triggering Worker…"):
                tick_res = trigger_worker_tick(settings)
                fetch_worker_jobs(repo, settings)
                if tick_res and tick_res.get("ok"):
                    r = tick_res.get("result", {})
                    st.success(
                        f"Published: {r.get('published', 0)}, "
                        f"Claimed: {r.get('claimed', 0)}"
                    )
                else:
                    st.info(f"Worker response: {tick_res}")
            st.rerun()

    with col_force:
        if st.button(
            "🧪 Publish ALL Today (Test)",
            use_container_width=True,
            help="Override all scheduled dates to TODAY and publish all posts immediately to Facebook for testing",
        ):
            with st.spinner("Setting all posts to Due Now and publishing to Facebook…"):
                force_res = force_publish_all_today(
                    repo,
                    settings,
                    campaign.campaign_id,
                    rev.revision_id if rev else 1,
                )
                pub = force_res.get("published", 0)
                if pub > 0:
                    st.success(f"🎉 Successfully published {pub} post(s) to Facebook!")
                else:
                    st.info(f"Worker tick completed. Claimed: {force_res.get('claimed', 0)}, Published: {pub}. Check table below.")
            st.rerun()

    # ── Daily Post Tracker (Indications & Schedule) ───────────────────
    st.markdown("---")
    st.markdown("### 📅 Daily Schedule & Post Tracker")
    st.caption("Here is where you check in everyday to see exactly which posts are published, scheduled, or need attention.")

    if jobs:
        # Sort jobs by scheduled_at ascending
        sorted_jobs = sorted(jobs, key=lambda j: j.scheduled_at or "")

        # Find the next upcoming job
        next_job = next(
            (j for j in sorted_jobs if j.status in {JobStatus.DRAFT, JobStatus.QUEUED, JobStatus.APPROVED}),
            None,
        )

        # Highlight box for today / next action
        if failed_count > 0:
            st.error(f"⚠️ **Attention Needed:** {failed_count} post(s) failed. Check the table below for details.")
        elif next_job:
            st.info(
                f"⏳ **Next Post in Line:** `{next_job.post_id}` scheduled for **{next_job.scheduled_at}** to **{conn.page_name if conn else 'Facebook'}**"
            )
        elif published_count > 0 and published_count == len(sorted_jobs):
            st.success("🎉 **All scheduled posts in this campaign have been published!**")

        # Visual Table of all posts
        table_rows = []
        for j in sorted_jobs:
            if j.status == JobStatus.PUBLISHED:
                status_icon = "🟢 Published"
            elif j.status in {JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_PERMANENT}:
                status_icon = "🔴 Failed"
            elif j.status == JobStatus.QUEUED:
                status_icon = "⏳ Queued (Auto-Publishing)"
            else:
                status_icon = f"⚪ {j.status.value}"

            row_data = {
                "Post": j.post_id,
                "Status": status_icon,
                "Scheduled Time": j.scheduled_at or "Immediate",
                "FB Post ID": j.remote_post_id or "—",
                "Last Error": (j.last_error_class.value if j.last_error_class else "None") if j.status in {JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_PERMANENT} else "—",
            }
            table_rows.append(row_data)

        st.dataframe(table_rows, use_container_width=True)
    else:
        st.info("No posts queued yet. Complete Step 1 and Step 2 above to load your campaign.")


if __name__ == "__main__":
    render()
