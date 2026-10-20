"""Quick Campaign – Guided Step-by-Step Campaign Creation & Scheduling.

Intuitive 5-step workflow:
1. Platforms & Campaign Selection
2. Content Upload (CSV plan & Image ZIP)
3. Review, Approve & Platform Previews (Facebook & Instagram)
4. Target Account & Schedule Settings
5. Preflight Validation & Explicit Push
"""
from __future__ import annotations

import io
from pathlib import Path
import tempfile
import zipfile
import streamlit as st

from advertfloz.application.services.campaign_import import ImportLimits, assemble_import
from advertfloz.application.services.campaign_revision import commit_import
from advertfloz.domain.enums import Platform, ProductionState
from advertfloz.infrastructure.worker_client import (
    activate_and_push_campaign,
    fetch_worker_jobs,
    force_publish_all_today,
    sync_meta_pages,
    sync_remote_connections,
)
from advertfloz.ui.components.status import chip
from advertfloz.ui.runtime import get_repo, get_settings


def _extract_zips_to_media(zips_data: list[tuple[str, bytes]], target_dir: Path | str = "data/media") -> int:
    """Extract JPEG/PNG image files from zip bytes into media directory."""
    dest = Path(target_dir)
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for _, zbytes in zips_data:
        try:
            with zipfile.ZipFile(io.BytesIO(zbytes), "r") as zf:
                for member in zf.infolist():
                    if not member.is_dir() and member.filename.lower().endswith((".jpg", ".jpeg", ".png")):
                        fn = Path(member.filename).name
                        (dest / fn).write_bytes(zf.read(member.filename))
                        count += 1
        except Exception:
            pass
    return count


def render() -> None:
    settings = get_settings()
    repo = get_repo()

    st.markdown('<div class="afz-page-title">⚡ Quick Campaign</div>', unsafe_allow_html=True)
    st.caption("Create, preview, schedule, and push social media campaigns across Facebook and Instagram.")

    # Multi-step state tracking
    if "qc_step" not in st.session_state:
        st.session_state["qc_step"] = 1
    if "qc_platforms" not in st.session_state:
        st.session_state["qc_platforms"] = ["facebook"]
    if "qc_campaign_id" not in st.session_state:
        campaigns = repo.list_campaigns()
        st.session_state["qc_campaign_id"] = campaigns[-1].campaign_id if campaigns else "campaign-1"
    st.session_state.setdefault("qc_plan_data", None)
    st.session_state.setdefault("qc_zip_data", [])
    st.session_state.setdefault("qc_committed", False)

    step = st.session_state["qc_step"]

    # ELI5 Callout Tutorial / Helper Wizard
    eli5_tips = {
        1: "👶 **ELI5 Step 1**: Where do you want your posts to go? Tick Facebook, Instagram, or both. Then give your project a friendly name!",
        2: "👶 **ELI5 Step 2**: Drop your spreadsheet (.csv) and your pictures (.zip) into the boxes below. We automatically link each caption to its photo!",
        3: "👶 **ELI5 Step 3**: Check your posts on real phone mockups! Flip between posts using the selector below and click 'Approve All Images' when happy.",
        4: "👶 **ELI5 Step 4**: Pick the Facebook Page you want to publish as (e.g. MusikFlo, Rashinos) and your local timezone.",
        5: "👶 **ELI5 Step 5**: Final safety check! When all 4 checkmarks are green, hit 'Schedule & Push' to let Cloudflare publish them automatically on time.",
    }

    if st.session_state.get("show_eli5_tutorial", True):
        with st.container():
            c_tip, c_skip = st.columns([5, 1])
            with c_tip:
                st.info(eli5_tips.get(step, "Follow the guided steps below."))
            with c_skip:
                if st.button("Skip Tips", key="skip_tutorial_btn", help="Hide tutorial helpers"):
                    st.session_state["show_eli5_tutorial"] = False
                    st.rerun()

    # Step Progress Indicator
    steps = [
        "1. Platforms & Campaign",
        "2. Upload Content",
        "3. Review & Previews",
        "4. Target & Schedule",
        "5. Validate & Push",
    ]

    p_cols = st.columns(len(steps))
    for i, s_name in enumerate(steps, 1):
        with p_cols[i - 1]:
            if i == step:
                st.markdown(f"**🔷 {s_name}**")
            elif i < step:
                st.markdown(f"✅ {s_name}")
            else:
                st.markdown(f"<span style='color:var(--afz-text-alt);'>⚪ {s_name}</span>", unsafe_allow_html=True)

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════
    #  STEP 1: PLATFORMS & CAMPAIGN
    # ═════════════════════════════════════════════════════════════════
    if step == 1:
        st.markdown("### Step 1 · Select Platforms & Campaign Pipeline")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Target Platforms**")
            p_fb = st.checkbox("📘 Facebook", value="facebook" in st.session_state["qc_platforms"])
            p_ig = st.checkbox("📸 Instagram", value="instagram" in st.session_state["qc_platforms"])

            selected_platforms = []
            if p_fb:
                selected_platforms.append("facebook")
            if p_ig:
                selected_platforms.append("instagram")

            if not selected_platforms:
                st.warning("Please select at least one platform.")

        with c2:
            st.markdown("**Campaign Pipeline**")
            campaigns = repo.list_campaigns()
            camp_options = [c.campaign_id for c in campaigns] + ["➕ Create New Pipeline…"]

            curr_val = st.session_state["qc_campaign_id"]
            init_idx = camp_options.index(curr_val) if curr_val in camp_options else 0

            chosen_pipeline = st.selectbox(
                "Select existing or create new:",
                options=camp_options,
                index=init_idx,
            )

            if chosen_pipeline == "➕ Create New Pipeline…":
                new_name = st.text_input("New Pipeline Name", placeholder="e.g. MusikFlo Fall Sprint 2026")
                new_id = new_name.lower().replace(" ", "-").replace("_", "-").strip() if new_name else ""
                st.caption(f"Pipeline ID: `{new_id or 'new-pipeline'}`")
                target_id = new_id or "new-pipeline"
            else:
                target_id = chosen_pipeline

        st.markdown("---")
        _, next_c = st.columns([4, 1])
        with next_c:
            if st.button("Next: Upload Content ➡️", type="primary", use_container_width=True, disabled=not selected_platforms):
                st.session_state["qc_platforms"] = selected_platforms
                st.session_state["qc_campaign_id"] = target_id
                st.session_state["qc_step"] = 2
                st.rerun()

    # ═════════════════════════════════════════════════════════════════
    #  STEP 2: UPLOAD CONTENT
    # ═════════════════════════════════════════════════════════════════
    elif step == 2:
        active_id = st.session_state["qc_campaign_id"]
        st.markdown(f"### Step 2 · Upload Content for Pipeline `{active_id}`")
        st.caption("Upload your campaign schedule spreadsheet (CSV) and companion images (ZIP).")

        col_csv, col_zip = st.columns(2)
        with col_csv:
            csv_file = st.file_uploader("📄 Campaign Plan CSV", type=["csv"], help="Contains post IDs, dates, and captions")
            if csv_file:
                st.session_state["qc_plan_data"] = (csv_file.name, csv_file.getvalue())
                st.session_state["qc_committed"] = False
            if st.session_state["qc_plan_data"]:
                pname, pbytes = st.session_state["qc_plan_data"]
                st.success(f"✅ Loaded `{pname}` ({len(pbytes):,} bytes)")

        with col_zip:
            zip_files = st.file_uploader("🗂️ Image ZIP Archive", type=["zip"], accept_multiple_files=True, help="ZIP containing 1.jpg, 2.jpg…")
            if zip_files:
                st.session_state["qc_zip_data"] = [(f.name, f.getvalue()) for f in zip_files]
                _extract_zips_to_media(st.session_state["qc_zip_data"])
                st.session_state["qc_committed"] = False
            if st.session_state["qc_zip_data"]:
                total_kb = sum(len(b) for _, b in st.session_state["qc_zip_data"]) // 1024
                st.success(f"✅ Loaded {len(st.session_state['qc_zip_data'])} ZIP archive(s) ({total_kb:,} KB)")

        # Auto-validate and import
        plan_item = st.session_state.get("qc_plan_data")
        zip_items = st.session_state.get("qc_zip_data")

        # Check existing posts in database for this campaign
        existing_rev = repo.latest_revision(active_id) if repo.get_campaign(active_id) else None
        db_posts = repo.list_posts(active_id, existing_rev.revision_id if existing_rev else 1) if repo.get_campaign(active_id) else []

        if plan_item and (zip_items or Path("data/media").exists()):
            try:
                with tempfile.TemporaryDirectory(prefix="qc_up_") as tmpdir:
                    tmppath = Path(tmpdir)
                    plan_path = tmppath / plan_item[0]
                    plan_path.write_bytes(plan_item[1])

                    zpaths = []
                    for zn, zb in (zip_items or []):
                        zp = tmppath / zn
                        zp.write_bytes(zb)
                        zpaths.append(zp)

                    limits = ImportLimits(
                        max_image_bytes=settings.max_image_bytes,
                        max_expanded_bytes=settings.max_expanded_bytes,
                        max_archive_bytes=settings.max_archive_bytes,
                    )

                    with st.spinner("Validating content plan and companion images…"):
                        res = assemble_import(
                            campaign_id=active_id,
                            campaign_name=active_id,
                            revision_id=1,
                            plan_path=plan_path,
                            zip_paths=zpaths if zpaths else None,
                            limits=limits,
                        )

                    blocking = [i for i in res.issues if i.is_blocking]
                    if blocking:
                        st.error(f"❌ {len(blocking)} issue(s) detected in plan:")
                        for b in blocking:
                            st.caption(f"• Row {b.row or 'Header'}: {b.message} ({b.rule})")
                    else:
                        st.session_state["qc_assembled_res"] = res
                        # Auto-commit so posts are never lost
                        if not st.session_state.get("qc_committed") or len(db_posts) == 0:
                            commit_import(repo, res, campaign_name=active_id)
                            st.session_state["qc_committed"] = True
                            db_posts = repo.list_posts(active_id, 1)

                        st.success(f"🎉 **Validation Successful!** {len(res.posts)} posts loaded with {len(res.assets)} companion images into pipeline `{active_id}`.")
                        if res.warnings:
                            with st.expander(f"ℹ️ {len(res.warnings)} non-blocking note(s)"):
                                for w in res.warnings:
                                    st.caption(f"• {w.message}")

            except Exception as e:
                st.error(f"⚠️ Validation encountered an unexpected issue: {e}")
        elif db_posts:
            st.info(f"ℹ️ Pipeline `{active_id}` currently has **{len(db_posts)} posts** saved in database. You can proceed to Review or upload new files above to replace them.")

        st.markdown("---")
        back_c, _, next_c = st.columns([1, 3, 1])
        with back_c:
            if st.button("⬅️ Back"):
                st.session_state["qc_step"] = 1
                st.rerun()
        with next_c:
            curr_posts = repo.list_posts(active_id, 1) if repo.get_campaign(active_id) else []
            has_posts = len(curr_posts) > 0 or st.session_state.get("qc_assembled_res") is not None
            if st.button("Next: Review & Previews ➡️", type="primary", use_container_width=True, disabled=not has_posts):
                # Ensure committed before advancing
                stored_res = st.session_state.get("qc_assembled_res")
                if stored_res and (not st.session_state.get("qc_committed") or len(curr_posts) == 0):
                    commit_import(repo, stored_res, campaign_name=active_id)
                    st.session_state["qc_committed"] = True
                st.session_state["qc_step"] = 3
                st.rerun()

    # ═════════════════════════════════════════════════════════════════
    #  STEP 3: REVIEW, APPROVE & PLATFORM PREVIEWS
    # ═════════════════════════════════════════════════════════════════
    elif step == 3:
        active_id = st.session_state["qc_campaign_id"]
        campaign = repo.get_campaign(active_id)
        rev = repo.latest_revision(active_id) if campaign else None
        posts = repo.list_posts(active_id, rev.revision_id if rev else 1) if campaign else []
        all_assets = repo.list_assets()
        post_img_ids = {p.image_id for p in posts}
        assets = [a for a in all_assets if a.image_id in post_img_ids] if posts else all_assets
        conn = repo.get_connection(Platform.FACEBOOK)
        brand_name = conn.page_name if (conn and conn.page_name) else "Official Brand Page"

        st.markdown("### Step 3 · Review, Approve & Platform Previews")

        # Approval status
        total_assets = len(assets)
        approved_count = sum(1 for a in assets if a.approved)

        col_app1, col_app2 = st.columns([3, 2])
        with col_app1:
            st.markdown(
                f"Asset Approval Status: {chip(f'{approved_count}/{total_assets} Approved', 'success' if approved_count == total_assets else 'warning')}",
                unsafe_allow_html=True,
            )
        with col_app2:
            if approved_count < total_assets:
                if st.button("✅ Approve All Images Now", type="primary", use_container_width=True):
                    for a in assets:
                        repo.update_production_state(a.image_id, ProductionState.APPROVED, approved=True)
                    st.success("All images approved.")
                    st.rerun()

        st.markdown("---")
        st.markdown("#### 📱 Platform Previews")

        if posts:
            post_labels = [f"Post #{i+1} (ID: {p.post_id}) · Scheduled for {p.scheduled_at}" for i, p in enumerate(posts)]
            sel_idx = st.selectbox("Choose post to preview:", range(len(posts)), format_func=lambda i: post_labels[i])
            sample_post = posts[sel_idx]
        else:
            sample_post = None

        sample_img = None
        if sample_post:
            candidates = [
                f"data/media/{sample_post.image_id}.jpg",
                f"data/media/{sample_post.image_id}.jpeg",
                f"data/media/{sample_post.image_id}.png",
                f"data/media/{sample_post.image_id}",
            ]
            sample_img = next((c for c in candidates if Path(c).exists()), None)

        tab_fb, tab_ig = st.tabs(["📘 Facebook Feed Preview", "📸 Instagram Post Preview"])

        with tab_fb:
            st.markdown(
                f"""
                <div style="max-width:480px; border:1px solid var(--afz-border); border-radius:12px; background:var(--afz-surface); padding:16px;">
                    <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
                        <div style="width:40px; height:40px; border-radius:50%; background:#1877F2; display:flex; align-items:center; justify-content:center; color:white; font-weight:bold;">f</div>
                        <div>
                            <b>{brand_name}</b><br>
                            <span style="font-size:12px; color:var(--afz-text-alt);">Sponsored · Just now</span>
                        </div>
                    </div>
                """,
                unsafe_allow_html=True,
            )
            caption_fb = (sample_post.facebook_caption or sample_post.caption) if sample_post else "Exciting announcement coming soon!"
            st.markdown(f"<div style='margin-bottom:10px;'>{caption_fb}</div>", unsafe_allow_html=True)
            if sample_img:
                st.image(sample_img, width=440)
            elif sample_post:
                st.info(f"Image `{sample_post.image_id}` not found on disk. Upload companion ZIP in Step 2.")
            st.markdown(
                """
                    <div style="display:flex; justify-content:space-around; border-top:1px solid var(--afz-border); margin-top:12px; padding-top:8px; font-size:13px; color:var(--afz-text-alt);">
                        <span>👍 Like</span>
                        <span>💬 Comment</span>
                        <span>↗️ Share</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with tab_ig:
            st.markdown(
                f"""
                <div style="max-width:440px; border:1px solid var(--afz-border); border-radius:12px; background:var(--afz-surface); padding:16px;">
                    <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
                        <div style="width:36px; height:36px; border-radius:50%; background:linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888); display:flex; align-items:center; justify-content:center; color:white; font-weight:bold;">📸</div>
                        <div>
                            <b>{brand_name.lower().replace(' ', '_')}</b><br>
                            <span style="font-size:12px; color:var(--afz-text-alt);">Original audio</span>
                        </div>
                    </div>
                """,
                unsafe_allow_html=True,
            )
            if sample_img:
                st.image(sample_img, width=400)
            caption_ig = (sample_post.instagram_caption or sample_post.caption) if sample_post else "Fresh campaign drop! 🚀 #marketing #launch"
            st.markdown(
                f"""
                    <div style="display:flex; gap:16px; margin:10px 0; font-size:18px;">
                        <span>❤️</span><span>💬</span><span>✈️</span>
                    </div>
                    <div style="font-size:13px;"><b>{brand_name.lower().replace(' ', '_')}</b> {caption_ig}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("---")
        back_c, _, next_c = st.columns([1, 3, 1])
        with back_c:
            if st.button("⬅️ Back"):
                st.session_state["qc_step"] = 2
                st.rerun()
        with next_c:
            if st.button("Next: Target & Schedule ➡️", type="primary", use_container_width=True):
                st.session_state["qc_step"] = 4
                st.rerun()

    # ═════════════════════════════════════════════════════════════════
    #  STEP 4: TARGET & SCHEDULE
    # ═════════════════════════════════════════════════════════════════
    elif step == 4:
        active_id = st.session_state["qc_campaign_id"]
        st.markdown(f"### Step 4 · Target Accounts & Schedule for `{active_id}`")

        # Fetch live Meta pages
        if settings.worker_configured and "qc_fb_pages" not in st.session_state:
            res = sync_meta_pages(repo, settings)
            if res and res.get("pages"):
                st.session_state["qc_fb_pages"] = res["pages"]

        pages = st.session_state.get("qc_fb_pages", [])
        conn = repo.get_connection(Platform.FACEBOOK)

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.markdown("**Facebook Target Page**")
            if pages:
                cur_idx = 0
                for idx, p in enumerate(pages):
                    if conn and p["id"] == conn.page_id:
                        cur_idx = idx
                        break

                chosen_page = st.selectbox(
                    "Publish posts to Page:",
                    options=pages,
                    index=cur_idx,
                    format_func=lambda p: f"📄 {p.get('name')} (ID: {p.get('id')})",
                )
                if chosen_page and conn and chosen_page["id"] != conn.page_id:
                    if st.button(f"Confirm Switch to {chosen_page.get('name')}"):
                        sync_meta_pages(repo, settings, page_id=chosen_page["id"])
                        st.success(f"Target page set to {chosen_page.get('name')}")
                        st.rerun()
            else:
                st.info(f"Targeting: **{conn.page_name if conn else 'Connected Facebook Page'}**")

        with col_t2:
            st.markdown("**Schedule & Timezone**")
            st.selectbox("Default Timezone", options=["Asia/Kolkata", "UTC", "America/New_York", "Europe/London"], index=0)
            st.caption("All CSV schedule times are interpreted in this timezone.")

        st.markdown("---")
        back_c, _, next_c = st.columns([1, 3, 1])
        with back_c:
            if st.button("⬅️ Back"):
                st.session_state["qc_step"] = 3
                st.rerun()
        with next_c:
            if st.button("Next: Preflight & Push ➡️", type="primary", use_container_width=True):
                st.session_state["qc_step"] = 5
                st.rerun()

    # ═════════════════════════════════════════════════════════════════
    #  STEP 5: PREFLIGHT VALIDATION & EXPLICIT PUSH
    # ═════════════════════════════════════════════════════════════
    elif step == 5:
        active_id = st.session_state["qc_campaign_id"]
        campaign = repo.get_campaign(active_id)
        rev = repo.latest_revision(active_id) if campaign else None
        posts = repo.list_posts(active_id, rev.revision_id if rev else 1) if campaign else []
        assets = repo.list_assets()
        conn = repo.get_connection(Platform.FACEBOOK)

        st.markdown("### Step 5 · Preflight Validation & Explicit Push")
        st.caption("Verify final checklist before activating the publishing pipeline.")

        chk1 = conn is not None and conn.page_id != ""
        chk2 = settings.worker_configured
        chk3 = len(posts) > 0
        chk4 = all(a.approved for a in assets if a.image_id in {p.image_id for p in posts}) if posts else False

        v1, v2, v3, v4 = st.columns(4)
        v1.markdown(f"**Target Page**: {'✅ ' + conn.page_name if chk1 else '❌ Missing'}")
        v2.markdown(f"**Worker & R2**: {'✅ Connected' if chk2 else '❌ Not configured'}")
        v3.markdown(f"**Content Posts**: {'✅ ' + str(len(posts)) + ' posts' if chk3 else '❌ None'}")
        v4.markdown(f"**Images Approved**: {'✅ All approved' if chk4 else '⚠️ Pending'}")

        st.markdown("---")

        all_ready = chk1 and chk2 and chk3 and chk4

        if all_ready:
            st.success("🎉 All preflight checks passed! Ready to schedule and push to Cloudflare.")
        else:
            st.warning("⚠️ Some preflight conditions require attention before pushing.")

        col_push, col_now, col_pipe = st.columns([1.5, 1.5, 1.2])
        with col_push:
            if st.button("🚀 Push & Schedule to Cloudflare", type="primary", disabled=not all_ready, use_container_width=True, help="Schedules posts in Cloudflare D1 to be posted at their exact CSV times."):
                with st.spinner("Pushing campaign, uploading media to R2, and syncing schedule with D1…"):
                    res = activate_and_push_campaign(
                        repo,
                        settings,
                        active_id,
                        rev.revision_id if rev else 1,
                    )
                    fetch_worker_jobs(repo, settings)

                if res.get("ok"):
                    st.success(f"🎉 Pipeline '{active_id}' activated! {res.get('images_uploaded')} images uploaded to R2, {res.get('jobs_queued')} jobs queued in D1.")
                else:
                    st.info(f"Queued {res.get('jobs_queued')} jobs. Sync status: {res.get('sync_response')}")

        with col_now:
            if st.button("⚡ Publish Due Posts Right Now", disabled=not all_ready, use_container_width=True, help="Immediately triggers the worker to post any due posts right away."):
                with st.spinner("Dispatching due posts to Facebook/Instagram right now…"):
                    f_res = force_publish_all_today(
                        repo,
                        settings,
                        active_id,
                        rev.revision_id if rev else 1,
                    )
                st.success(f"Dispatched! Published: {f_res.get('published', 0)}, Claimed: {f_res.get('claimed', 0)}")
                st.rerun()

        with col_pipe:
            if st.button("👉 View in Pipelines", use_container_width=True):
                st.session_state["selected_pipeline_id"] = active_id
                st.switch_page("advertfloz/ui/pages/pipelines.py")

        st.markdown("---")
        back_c, _ = st.columns([1, 4])
        with back_c:
            if st.button("⬅️ Back"):
                st.session_state["qc_step"] = 4
                st.rerun()


if __name__ == "__main__":
    render()
