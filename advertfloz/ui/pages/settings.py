"""Settings & Recovery (PRD §4.14)."""
from __future__ import annotations

import streamlit as st

from advertfloz.application.services import backups
from advertfloz.diagnostics import Status, run_cost_gate, run_doctor
from advertfloz.ui.components.status import chip
from advertfloz.ui.runtime import get_repo, get_settings


def render() -> None:
    settings = get_settings()
    repo = get_repo()
    st.markdown('<div class="afz-page-title">Settings &amp; Recovery</div>', unsafe_allow_html=True)

    st.markdown('<div class="afz-section-title">Configuration (values shown are non-secret)</div>', unsafe_allow_html=True)
    st.dataframe([{"key": k, "value": str(v)} for k, v in settings.redacted().items()], width="stretch")
    st.caption("Secret values are never displayed. Configure them in .streamlit/secrets.toml, deployment secrets or the OS keyring.")

    st.markdown('<div class="afz-section-title">Posting preferences</div>', unsafe_allow_html=True)
    st.text_input("Default timezone", settings.default_timezone, disabled=True)
    st.text_input("Import image byte limit", str(settings.max_image_bytes), disabled=True)
    st.text_input("Import expanded byte limit", str(settings.max_expanded_bytes), disabled=True)
    st.markdown(chip("No auto-upgrade · no paid fallback", "success")
                + ' <span class="afz-muted">AdvertFloz will not enable paid tiers or fall back to them automatically.</span>',
                unsafe_allow_html=True)

    st.markdown('<div class="afz-section-title">Backups</div>', unsafe_allow_html=True)
    runs = repo.list_backup_runs()
    if runs:
        st.dataframe(
            [{"id": r.backup_id, "created": r.created_at, "bytes": r.byte_size,
              "includes_secrets": r.includes_secrets, "verified": r.verified, "restore_drill": r.restore_drill_at}
             for r in runs],
            width="stretch",
        )
    if st.button("Create backup now", type="primary"):
        run = backups.create_backup(repo, "backups")
        st.success(f"Backup {run.backup_id} created ({run.byte_size} bytes), secret-free and verified.")
        st.rerun()
    if runs and st.button("Record a restore drill"):
        backups.record_restore_drill(repo, runs[0].backup_id)
        st.success("Restore drill recorded.")
    st.caption("Restore requires the separate TOKEN_ENCRYPTION_KEY from your secret manager; see "
               "docs/RUNBOOKS/restore.md. A missing key means you must reconnect platforms, not fake the tokens.")

    st.markdown('<div class="afz-section-title">Cost gate (zero-spend)</div>', unsafe_allow_html=True)
    gate = run_cost_gate(settings)
    tone = "success" if gate.allowed else "danger"
    st.markdown(chip("GO" if gate.allowed else "NO-GO", tone) + f' <span class="afz-muted">{gate.reason}</span>',
                unsafe_allow_html=True)
    st.dataframe([{"check": c.name, "status": c.status.value, "detail": c.detail} for c in gate.checks],
                 width="stretch")

    st.markdown('<div class="afz-section-title">Diagnostics</div>', unsafe_allow_html=True)
    if st.button("Run doctor"):
        st.session_state["doctor"] = run_doctor(settings, repo)
    for diag in st.session_state.get("doctor", []):
        emit = {Status.OK: st.success, Status.WARNING: st.warning, Status.BLOCKED: st.error}[diag.status]
        emit(f"{diag.name}: {diag.detail}")


if __name__ == "__main__":
    render()
