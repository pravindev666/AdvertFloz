"""Incident detection (FR-032).

A missing daily digest or a stale heartbeat is itself an incident: the absence of visible API
errors does not prove health.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ...domain.enums import IncidentState, Severity
from ...domain.models import Incident
from ...infrastructure.persistence.local_sqlite import Repository
from .notifications import digest_is_stale
from .preflight import HEARTBEAT_STALE_MINUTES


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def create_incident(repo: Repository, *, severity: Severity, cause: str, diagnosis: str, remediation: str,
                    platform=None, post_id: str = "", retry_eligible: bool = False) -> Incident:
    incident = Incident(
        incident_id=_new_id(cause), severity=severity, cause=cause, platform=platform, post_id=post_id,
        diagnosis=diagnosis, remediation=remediation, retry_eligible=retry_eligible,
    )
    repo.add_incident(incident)
    return incident


def detect_health_incidents(repo: Repository, *, now: datetime | None = None, remote_mode: bool = False) -> list[Incident]:
    """Raise incidents for stale heartbeat and a missing/stale daily digest."""
    now = now or datetime.now(UTC)
    raised: list[Incident] = []

    if remote_mode:
        beat = repo.get_flag("worker_heartbeat_at") or repo.get_flag("scheduler_heartbeat_at")
        stale = True
        if beat:
            try:
                age = (now - datetime.fromisoformat(beat.replace("Z", "+00:00"))).total_seconds() / 60
                stale = age > HEARTBEAT_STALE_MINUTES
            except ValueError:
                stale = True
        if stale:
            raised.append(
                create_incident(
                    repo, severity=Severity.DANGER, cause="stale_worker",
                    diagnosis="Remote worker heartbeat is missing or older than the stale threshold.",
                    remediation="Check the Worker Cron schedule and logs; verify D1 connectivity. "
                                "The independent uptime monitor should also be alerting.",
                )
            )

    if digest_is_stale(repo, now):
        raised.append(
            create_incident(
                repo, severity=Severity.WARNING, cause="missing_digest",
                diagnosis="The daily health digest has not been emitted recently.",
                remediation="Run the digest command from the scheduler process; confirm alert delivery.",
            )
        )
    return raised


def list_open_incidents(repo: Repository) -> list[Incident]:
    return repo.list_incidents(IncidentState.OPEN)


def acknowledge(repo: Repository, incident_id: str, actor: str = "operator") -> None:
    repo.acknowledge_incident(incident_id)
    repo.audit(actor, "incident.ack", incident_id, "operator acknowledged")
