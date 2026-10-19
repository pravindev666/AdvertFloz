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
from advertfloz.ui.runtime import get_repo, get_settings


def _save_uploads(files) -> list[Path]:
    paths: list[Path] = []
    upload_dir = Path(tempfile.mkdtemp(prefix="afz_upload_"))
    for uploaded in files or []:
        target = upload_dir / uploaded.name
        target.write_bytes(uploaded.getbuffer())
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


def render() -> None:
    settings = get_settings()
    repo: Repository = get_repo()
    st.markdown('<div class="afz-page-title">Campaign Import</div>', unsafe_allow_html=True)

    limits = ImportLimits(
        max_image_bytes=settings.max_image_bytes,
        max_expanded_bytes=settings.max_expanded_bytes,
        max_archive_bytes=settings.max_archive_bytes,
    )
    st.caption(
        f"Limits — image ≤ {limits.max_image_bytes // (1024*1024)} MB, archive ≤ "
        f"{limits.max_archive_bytes // (1024*1024)} MB, total expanded ≤ {limits.max_expanded_bytes // (1024*1024)} MB"
    )

    step = st.radio("Step", ["1 · Plan", "2 · Assets", "3 · Cross-checks", "4 · Validate", "5 · Review"], horizontal=True)

    if step.endswith("Plan"):
        st.file_uploader("campaign_plan.csv", type=["csv"], key="plan_csv")
    elif step.endswith("Assets"):
        st.file_uploader("Image ZIP parts (advertfloz_images_NNN_NNN.zip)", type=["zip"], accept_multiple_files=True, key="zip_parts")
    elif step.endswith("Cross-checks"):
        st.file_uploader("image_prompts.csv", type=["csv"], key="prompts_csv")
        st.file_uploader("campaign_manifest.json", type=["json"], key="manifest_json")
        st.file_uploader("365_day_prompt_library.md", type=["md"], key="lib_md")
        st.file_uploader("365_outcomes_driven_campaigns.md", type=["md"], key="outcomes_md")

    if step.endswith("Validate") or step.endswith("Review"):
        plan_file = st.session_state.get("plan_csv")
        if plan_file is None:
            st.warning("Select campaign_plan.csv in step 1 first.")
            return
        plan_paths = _save_uploads([plan_file])
        zip_paths = _save_uploads(st.session_state.get("zip_parts") or [])
        manifest_file = st.session_state.get("manifest_json")
        manifest_paths = _save_uploads([manifest_file]) if manifest_file is not None else []

        campaign_id = st.text_input("Campaign ID", value="campaign-1")
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

        if step.endswith("Review") and result.ok and result.mapping_complete():
            if st.button("Commit campaign revision", type="primary"):
                revision = commit_import(repo, result)
                st.success(f"Committed campaign revision {revision}. No rows were activated.")
            with st.expander("Contact sheet"):
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
        elif step.endswith("Review"):
            st.warning("Resolve blocking errors before committing. Partial imports cannot be activated.")


if __name__ == "__main__":
    render()
