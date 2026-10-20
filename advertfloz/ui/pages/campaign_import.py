"""Campaign Import wizard (FR-005, FR-006, FR-007, FR-010, PRD §4.4)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from advertfloz.application.services.campaign_import import ImportLimits, assemble_import
from advertfloz.application.services.campaign_revision import commit_import
from advertfloz.application.services.contact_sheet import (
    build_contact_sheet,
    render_text_manifest,
    tile_metadata,
)
from advertfloz.infrastructure.persistence.local_sqlite import Repository
from advertfloz.ui.components.tutorial import render_tutorial_callout
from advertfloz.ui.runtime import get_repo, get_settings


def _save_uploads(files_data: list[tuple[str, bytes]]) -> list[Path]:
    paths: list[Path] = []
    upload_dir = Path(tempfile.mkdtemp(prefix="afz_upload_"))
    for name, data in files_data:
        target = upload_dir / name
        target.write_bytes(data)
        paths.append(target)
    return paths


def _render_issues(issues) -> None:
    blocking = [i for i in issues if i.is_blocking]
    warnings = [i for i in issues if not i.is_blocking]
    if blocking:
        st.error(f"{len(blocking)} blocking error(s) — import cannot be committed")
        st.dataframe(
            [{"row": i.row, "field": i.field, "value": i.value, "rule": i.rule, "message": i.message} for i in blocking],
            width="stretch",
        )
    if warnings:
        with st.expander(f"{len(warnings)} warning(s)"):
            st.dataframe(
                [{"row": i.row, "field": i.field, "value": i.value, "rule": i.rule, "message": i.message} for i in warnings],
                width="stretch",
            )


def _persist_plan():
    """Callback: fires when the plan CSV uploader changes."""
    uploaded = st.session_state.get("plan_csv_uploader")
    if uploaded is not None:
        st.session_state["persisted_plan"] = (uploaded.name, uploaded.getvalue())


def _persist_zips():
    """Callback: fires when the ZIP uploader changes."""
    uploaded = st.session_state.get("zip_parts_uploader")
    if uploaded:
        st.session_state["persisted_zips"] = [(f.name, f.getvalue()) for f in uploaded]


def _persist_manifest():
    """Callback: fires when the manifest uploader changes."""
    uploaded = st.session_state.get("manifest_json_uploader")
    if uploaded is not None:
        st.session_state["persisted_manifest"] = (uploaded.name, uploaded.getvalue())


def _go_to_step(new_step: str) -> None:
    st.session_state["pending_step"] = new_step
    st.rerun()


def render() -> None:
    settings = get_settings()
    repo: Repository = get_repo()
    st.markdown('<div class="afz-page-title">Campaign Import</div>', unsafe_allow_html=True)
    render_tutorial_callout("Campaign Import")

    limits = ImportLimits(
        max_image_bytes=settings.max_image_bytes,
        max_expanded_bytes=settings.max_expanded_bytes,
        max_archive_bytes=settings.max_archive_bytes,
    )
    st.caption(
        f"Limits — image ≤ {limits.max_image_bytes // (1024*1024)} MB, archive ≤ "
        f"{limits.max_archive_bytes // (1024*1024)} MB, total expanded ≤ {limits.max_expanded_bytes // (1024*1024)} MB"
    )

    # Initialize persistent state so switching steps never loses uploaded files
    st.session_state.setdefault("persisted_plan", None)
    st.session_state.setdefault("persisted_zips", [])
    st.session_state.setdefault("persisted_manifest", None)

    step_options = ["1 · Plan", "2 · Assets", "3 · Cross-checks", "4 · Validate", "5 · Review"]
    if "pending_step" in st.session_state:
        st.session_state["import_step_radio"] = st.session_state.pop("pending_step")
    if "import_step_radio" not in st.session_state:
        st.session_state["import_step_radio"] = "1 · Plan"

    step = st.radio(
        "Step",
        step_options,
        horizontal=True,
        key="import_step_radio",
    )
    st.session_state["current_import_step"] = step

    # ---- Persistent upload status banner ----
    _show_upload_status()

    # ------------------ STEP 1: PLAN ------------------
    if step.endswith("Plan"):
        st.markdown("### Step 1: Upload Campaign Plan")
        st.caption("Upload your primary `campaign_plan.csv` specifying post schedules, captions, and platforms.")
        st.file_uploader(
            "campaign_plan.csv",
            type=["csv"],
            key="plan_csv_uploader",
            on_change=_persist_plan,
        )

        if st.session_state["persisted_plan"]:
            plan_name, plan_data = st.session_state["persisted_plan"]
            st.success(f"✅ Loaded: `{plan_name}` ({len(plan_data):,} bytes)")
            if st.button("Next: Step 2 · Assets ➔", type="primary"):
                _go_to_step("2 · Assets")

    # ------------------ STEP 2: ASSETS ------------------
    elif step.endswith("Assets"):
        st.markdown("### Step 2: Upload Image ZIP Archive")
        st.caption("Upload your ZIP archive containing JPEG images (`1.jpg` ... `N.jpg`) at the root or inside one subfolder.")
        st.file_uploader(
            "Image ZIP parts (advertfloz_images_NNN_NNN.zip)",
            type=["zip"],
            accept_multiple_files=True,
            key="zip_parts_uploader",
            on_change=_persist_zips,
        )

        if st.session_state["persisted_zips"]:
            total_size = sum(len(d) for _, d in st.session_state["persisted_zips"])
            st.success(f"✅ Loaded {len(st.session_state['persisted_zips'])} ZIP archive(s) ({total_size // 1024:,} KB)")
            for name, data in st.session_state["persisted_zips"]:
                st.caption(f"• `{name}` ({len(data):,} bytes)")
            
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("Next: Step 4 · Validate ➔", type="primary"):
                    _go_to_step("4 · Validate")
            with col2:
                if st.button("Go to Step 3 · Optional Cross-checks ➔"):
                    _go_to_step("3 · Cross-checks")

    # ------------------ STEP 3: CROSS-CHECKS ------------------
    elif step.endswith("Cross-checks"):
        st.markdown("### Step 3: Optional Cross-Checks")
        st.caption("Upload supporting campaign package files for strict schema validation against AI output.")
        st.file_uploader(
            "campaign_manifest.json (Optional)",
            type=["json"],
            key="manifest_json_uploader",
            on_change=_persist_manifest,
        )
        st.file_uploader("image_prompts.csv (Optional)", type=["csv"], key="prompts_csv_uploader")
        st.file_uploader("365_day_prompt_library.md (Optional)", type=["md"], key="lib_md_uploader")
        st.file_uploader("365_outcomes_driven_campaigns.md (Optional)", type=["md"], key="outcomes_md_uploader")

        if st.button("Proceed to Step 4 · Validate ➔", type="primary"):
            _go_to_step("4 · Validate")

    # ------------------ STEP 4 & 5: VALIDATE & REVIEW ------------------
    if step.endswith("Validate") or step.endswith("Review"):
        plan_item = st.session_state.get("persisted_plan")
        if plan_item is None:
            st.warning("⚠️ Please upload `campaign_plan.csv` in **Step 1 · Plan** first.")
            if st.button("← Go to Step 1 · Plan"):
                _go_to_step("1 · Plan")
            return

        zip_items = st.session_state.get("persisted_zips") or []
        if not zip_items:
            st.warning("⚠️ Please upload your image ZIP archive in **Step 2 · Assets** before validating.")
            if st.button("← Go to Step 2 · Assets"):
                _go_to_step("2 · Assets")
            return

        # Show current files being validated
        st.caption(f"Validating plan `{plan_item[0]}` with {len(zip_items)} image archive(s)")

        plan_paths = _save_uploads([plan_item])
        zip_paths = _save_uploads(zip_items)
        manifest_item = st.session_state.get("persisted_manifest")
        manifest_paths = _save_uploads([manifest_item]) if manifest_item is not None else []

        campaign_id = st.text_input("Campaign ID / Name", value="campaign-1")
        result = assemble_import(
            campaign_id=campaign_id,
            campaign_name=campaign_id,
            revision_id=1,
            plan_path=plan_paths[0],
            zip_paths=zip_paths,
            limits=limits,
            manifest_path=manifest_paths[0] if manifest_paths else None,
        )
        _render_issues(result.issues)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Rows", len(result.posts))
        c2.metric("Images", len(result.assets))
        c3.metric("Facebook jobs", result.platform_counts()["facebook"])
        c4.metric("Instagram jobs", result.platform_counts()["instagram"])
        st.caption(f"Date range {result.start_date} → {result.end_date} · timezone {result.default_timezone}")

        missing = result.missing_image_ids()
        if missing:
            st.error(f"Missing images: {missing[:30]}")

        # Review & Commit
        if step.endswith("Validate"):
            if result.ok and result.mapping_complete():
                st.success("🎉 **Validation Passed! All rows and images match with 0 errors.**")
                if st.button("Proceed to Step 5 · Review & Commit ➔", type="primary"):
                    _go_to_step("5 · Review")

        elif step.endswith("Review"):
            if result.ok and result.mapping_complete():
                st.markdown("### Step 5: Review & Commit")
                if st.button("🚀 Commit Campaign Revision", type="primary", use_container_width=True):
                    revision = commit_import(repo, result)
                    st.success(f"🎉 Committed campaign revision {revision}! All posts are scheduled and ready to view.")
                    st.info("👉 Check the **Calendar** in the sidebar to review your scheduled posts, 3x3 Instagram grid, and timeline.")
                
                with st.expander("🖼️ Contact Sheet (All Images)", expanded=True):
                    media = {}
                    store_dir = Path("data/media")
                    for image_id in result.assets:
                        candidate = store_dir / f"{image_id}.jpg"
                        if candidate.exists():
                            media[image_id] = candidate
                    png = build_contact_sheet(media)
                    if png:
                        st.image(png, width="stretch")
                    else:
                        st.caption("Thumbnails require Pillow and extracted media; showing manifest instead.")
                        post_by_image = {p.image_id: p.post_id for p in result.posts}
                        st.markdown(render_text_manifest(tile_metadata([], post_by_image)))
            else:
                st.warning("Resolve blocking errors before committing. Partial imports cannot be activated.")


def _show_upload_status():
    """Show a compact status bar of what's been uploaded so far."""
    parts = []
    if st.session_state.get("persisted_plan"):
        parts.append(f"📄 Plan: `{st.session_state['persisted_plan'][0]}`")
    if st.session_state.get("persisted_zips"):
        n = len(st.session_state["persisted_zips"])
        parts.append(f"🗂️ ZIP{'s' if n > 1 else ''}: {n} archive{'s' if n > 1 else ''}")
    if st.session_state.get("persisted_manifest"):
        parts.append(f"📋 Manifest: `{st.session_state['persisted_manifest'][0]}`")
    if parts:
        st.info(" · ".join(parts), icon="✅")


if __name__ == "__main__":
    render()

