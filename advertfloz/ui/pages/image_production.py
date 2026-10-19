"""Image Production board (FR-008, PRD §4.5)."""
from __future__ import annotations

import csv
import io
from pathlib import Path

import streamlit as st

from advertfloz.application.services.contact_sheet import build_contact_sheet
from advertfloz.domain.enums import MANUAL_PRODUCTION_STATES, ProductionState
from advertfloz.domain.scheduling import MIN_READY_DAYS, WARN_READY_DAYS
from advertfloz.ui.components.status import chip
from advertfloz.ui.runtime import get_repo


def render() -> None:
    repo = get_repo()
    st.markdown('<div class="afz-page-title">Image Production</div>', unsafe_allow_html=True)

    assets = repo.list_assets()
    if not assets:
        st.info("No assets yet. Import a campaign with image ZIP parts first.")
        return

    ready = repo.ready_synced_image_ids()
    ordered = [a.image_id for a in assets]
    consecutive = 0
    run = 0
    for image_id in ordered:
        run = run + 1 if image_id in ready else 0
        consecutive = max(consecutive, run)

    tone = "success" if consecutive >= WARN_READY_DAYS else ("warning" if consecutive >= MIN_READY_DAYS else "danger")
    st.markdown(
        f'<div class="afz-panel">{chip(f"{len(ready)} ready / {len(assets)} total", "info")} '
        f'{chip(f"{consecutive} consecutive days", tone)} '
        f'<span class="afz-muted">warn below {WARN_READY_DAYS}, block activation below {MIN_READY_DAYS}</span></div>',
        unsafe_allow_html=True,
    )

    view = st.radio("View", ["Board", "List"], horizontal=True)
    state_filter = st.multiselect("Production state", [s.value for s in ProductionState], default=[])

    filtered = [a for a in assets if not state_filter or a.production_state.value in state_filter]

    if view == "List":
        st.dataframe(
            [
                {
                    "image_id": a.image_id,
                    "filename": a.filename,
                    "state": a.production_state.value,
                    "approved": a.approved,
                    "sync": a.sync_state.value,
                    "sha256": a.sha256[:12],
                }
                for a in filtered
            ],
            width="stretch",
        )
    else:
        columns = st.columns(4)
        for index, asset in enumerate(filtered):
            with columns[index % 4]:
                post_id = f"P{asset.image_id:03d}"
                st.markdown(
                    f'<div class="afz-panel"><b class="afz-mono">{asset.image_id}.jpg</b><br>'
                    f'<span class="afz-muted">{post_id} · {asset.production_state.value}</span><br>'
                    f'{chip("approved" if asset.approved else "not approved", "success" if asset.approved else "warning")}</div>',
                    unsafe_allow_html=True,
                )
                media = Path("data/media") / f"{asset.image_id}.jpg"
                if media.exists():
                    st.image(str(media), width=140)

    st.markdown('<div class="afz-section-title">Mark production states (manual steps)</div>', unsafe_allow_html=True)
    unedited = [a for a in assets if a.production_state in MANUAL_PRODUCTION_STATES or a.production_state is ProductionState.PROMPT_READY]
    if unedited:
        options = {f"{a.image_id}.jpg ({a.production_state.value})": a.image_id for a in unedited}
        selected = st.selectbox("Asset", list(options))
        col1, col2, col3 = st.columns(3)
        if col1.button("Mark generated"):
            repo.update_production_state(options[selected], ProductionState.GENERATED)
            st.rerun()
        if col2.button("Mark overlay done"):
            repo.update_production_state(options[selected], ProductionState.OVERLAY_DONE)
            st.rerun()
        if col3.button("Approve", type="primary"):
            repo.update_production_state(options[selected], ProductionState.APPROVED, approved=True)
            repo.audit("operator", "asset.approve", str(options[selected]), "approved")
            st.rerun()

    st.markdown('<div class="afz-section-title">Exports</div>', unsafe_allow_html=True)
    media = {a.image_id: Path("data/media") / f"{a.image_id}.jpg" for a in assets if (Path("data/media") / f"{a.image_id}.jpg").exists()}
    png = build_contact_sheet(media)
    if png:
        st.download_button("Download contact sheet (PNG)", png, file_name="advertfloz_contact_sheet.png")
    st.download_button("Download production tracker (CSV)", _tracker_csv(assets), file_name="image_production_tracker.csv")


def _tracker_csv(assets) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["post_id", "image_id", "state", "approved", "sync_state", "sha256", "filename"])
    for asset in assets:
        writer.writerow([f"P{asset.image_id:03d}", asset.image_id, asset.production_state.value, asset.approved,
                         asset.sync_state.value, asset.sha256, asset.filename])
    return buffer.getvalue()


if __name__ == "__main__":
    render()
