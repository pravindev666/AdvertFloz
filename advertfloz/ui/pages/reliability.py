"""Reliability & Incidents (FR-028, FR-032, PRD §4.12)."""
from __future__ import annotations

import streamlit as st

from advertfloz.application.services import incidents as incidents_service
from advertfloz.application.services.health import build_overview
from advertfloz.application.services.notifications import digest_is_stale
from advertfloz.application.services.preflight import run_preflight
from advertfloz.domain.enums import IncidentState
from advertfloz.ui.components.summary import SummaryItem, summary_strip
from advertfloz.ui.runtime import get_repo, get_settings


def render() -> None:
    settings = get_settings()
    repo = get_repo()
    st.markdown('<div class="afz-page-title">Reliability &amp; Incidents</div>', unsafe_allow_html=True)

    if st.button("Scan for health incidents"):
        raised = incidents_service.detect_health_incidents(repo, remote_mode=settings.mode == "remote")
        st.success(f"{len(raised)} incident(s) recorded from the health scan.")

    ov = build_overview(repo, mode=settings.mode)
    summary_strip(st, [
        SummaryItem("Heartbeat", f"{ov.heartbeat_age_minutes} min ago" if ov.heartbeat_age_minutes is not None else "never",
                    "success" if ov.heartbeat_ok else "warning"),
        SummaryItem("Digest", "fresh" if not digest_is_stale(repo) else "missing/stale",
                    "success" if not digest_is_stale(repo) else "warning"),
        SummaryItem("UNKNOWN_OUTCOME", str(ov.unknown_outcomes), "danger" if ov.unknown_outcomes else "neutral"),
        SummaryItem("Asset buffer", f"{ov.buffer_days} day(s)", ov.buffer_status),
        SummaryItem("Latest backup", ov.latest_backup_at or "none", "neutral"),
        SummaryItem("Restore drill", ov.last_restore_drill_at or "never", "neutral"),
    ], columns=3)

    st.markdown('<div class="afz-section-title">Preflight (next 48 hours)</div>', unsafe_allow_html=True)
    report = run_preflight(repo, remote_mode=settings.mode == "remote")
    st.caption(f"{report.jobs_in_window} job(s) in window · {'BLOCKED' if not report.ok else 'clear'}")
    st.dataframe(
        [{"check": c.name, "status": c.status.value, "detail": c.detail} for c in report.checks],
        width="stretch",
    )

    st.markdown('<div class="afz-section-title">Incidents</div>', unsafe_allow_html=True)
    incidents = repo.list_incidents()
    if not incidents:
        st.info("No incidents recorded. Note: zero visible API errors does not by itself prove health.")
        return
    st.dataframe(
        [
            {
                "id": i.incident_id,
                "severity": i.severity.value,
                "state": i.state.value,
                "cause": i.cause,
                "platform": i.platform.value if i.platform else "",
                "post_id": i.post_id,
                "diagnosis": i.diagnosis,
                "remediation": i.remediation,
                "retry_eligible": i.retry_eligible,
                "created_at": i.created_at,
            }
            for i in incidents
        ],
        width="stretch",
    )
    open_ids = [i.incident_id for i in incidents if i.state is IncidentState.OPEN]
    if open_ids:
        chosen = st.selectbox("Acknowledge incident", open_ids)
        if st.button("Acknowledge"):
            incidents_service.acknowledge(repo, chosen)
            st.success(f"Acknowledged {chosen}.")
            st.rerun()


if __name__ == "__main__":
    render()
