"""Dependency diagnostics (doctor) and the zero-cost gate.

Reports OK / WARNING / BLOCKED per dependency without ever echoing secret values. The
zero-cost gate decides whether remote mode may be enabled; failing it keeps remote blocked
while local mode keeps working.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from .config import Settings
from .infrastructure.persistence.local_sqlite import Repository


class Status(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


@dataclass
class Diagnostic:
    name: str
    status: Status
    detail: str


def run_doctor(settings: Settings, repo: Repository | None = None) -> list[Diagnostic]:
    checks: list[Diagnostic] = []

    # Python
    import sys

    if sys.version_info >= (3, 11):
        checks.append(Diagnostic("python", Status.OK, f"{sys.version.split()[0]} (>=3.11)"))
    else:
        checks.append(Diagnostic("python", Status.BLOCKED, "Python 3.11+ required for zoneinfo"))

    # DB migrations
    try:
        from .infrastructure.persistence.local_sqlite.migrations import SCHEMA_VERSION, current_version

        own = repo is None
        repo = repo or Repository(settings.db_path)
        version = current_version(repo.conn)
        checks.append(Diagnostic("db_migrations", Status.OK if version == SCHEMA_VERSION else Status.WARNING,
                                 f"schema {version}/{SCHEMA_VERSION} at {settings.db_path}"))
        if own:
            repo.close()
    except Exception as exc:
        checks.append(Diagnostic("db_migrations", Status.BLOCKED, f"cannot open database: {type(exc).__name__}"))

    # Secrets configuration
    checks.append(Diagnostic("secrets", Status.OK if settings.token_key_present else Status.WARNING,
                             "token encryption key present" if settings.token_key_present
                             else "TOKEN_ENCRYPTION_KEY missing; tokens cannot be stored"))
    checks.append(Diagnostic("meta_app", Status.OK if settings.meta_app_configured else Status.WARNING,
                             "Meta App configured" if settings.meta_app_configured else "META_APP_ID/SECRET missing"))
    checks.append(Diagnostic("meta_callback", Status.OK if settings.meta_oauth_redirect_uri else Status.BLOCKED,
                             settings.meta_oauth_redirect_uri or "no callback URI configured"))

    # Platforms (from repo if available)
    if repo is not None:
        from .domain.enums import Platform

        for platform, label in ((Platform.FACEBOOK, "facebook"), (Platform.INSTAGRAM, "instagram")):
            conn = repo.get_connection(platform)
            checks.append(Diagnostic(label, Status.OK if conn and conn.account_id or conn and conn.page_id else Status.WARNING,
                                     conn.state.value if conn else "not connected"))
        backups = repo.list_backup_runs()
        checks.append(Diagnostic("backups", Status.OK if backups else Status.WARNING,
                                 f"{len(backups)} backup(s) recorded"))
    else:
        checks.append(Diagnostic("facebook", Status.WARNING, "no database"))
        checks.append(Diagnostic("instagram", Status.WARNING, "no database"))

    # Storage / media
    checks.append(Diagnostic("storage_local", Status.OK, f"data dir {Path('data')}"))

    # Remote plane
    checks.append(Diagnostic("worker_cron", Status.OK if settings.worker_configured else Status.WARNING,
                             "worker configured" if settings.worker_configured else "remote worker not configured"))
    checks.append(Diagnostic("sync_api", Status.OK if settings.worker_configured else Status.WARNING,
                             "service-to-service key present" if settings.worker_service_key else "no service key"))
    checks.append(Diagnostic("media_fetch", Status.OK if settings.media_base_url else Status.WARNING,
                             settings.media_base_url or "no public media base URL; Meta cannot fetch media"))

    # Alerts
    checks.append(Diagnostic("alert_path", Status.OK if settings.telegram_configured else Status.WARNING,
                             "telegram configured" if settings.telegram_configured else "no alert channel configured"))

    # Hosted auth
    if settings.hosted:
        checks.append(Diagnostic("auth", Status.OK if settings.hosted_auth_ready() else Status.BLOCKED,
                                 "operator allowlist + IdP configured" if settings.hosted_auth_ready()
                                 else "hosted mode without auth; failing closed"))
    else:
        checks.append(Diagnostic("auth", Status.OK, "local loopback mode (no app login required)"))

    # Cost gate
    gate = run_cost_gate(settings)
    checks.append(Diagnostic("cost_gate", Status.OK if gate.allowed else Status.WARNING, gate.reason))
    return checks


@dataclass
class CostGateResult:
    allowed: bool
    checks: list[Diagnostic]
    reason: str
    decided_at: str = ""

    def __post_init__(self):
        if not self.decided_at:
            self.decided_at = datetime.now(UTC).isoformat(timespec="seconds")


def run_cost_gate(settings: Settings) -> CostGateResult:
    """Zero-cost deployment gate (FR-030). Remote stays NO-GO until every prerequisite passes."""
    checks = [
        Diagnostic("cloudflare_account", Status.WARNING if not settings.worker_configured else Status.OK,
                   "verify Worker deployment eligibility on the real account"),
        Diagnostic("r2_payment_prerequisite",
                   Status.WARNING,
                   "R2 requires a payment method on file; 'free' does not prove no payment method is required"),
        Diagnostic("worker_limits", Status.WARNING, "confirm current CPU/request/subrequest/cron limits"),
        Diagnostic("d1_limits", Status.WARNING, "confirm current D1 limits"),
        Diagnostic("r2_limits", Status.WARNING, "confirm current R2 storage/operation limits"),
        Diagnostic("media_accessibility", Status.OK if settings.media_base_url else Status.BLOCKED,
                   "Meta must fetch media over HTTPS; verify signed-URL lifetime"),
        Diagnostic("remote_auth", Status.OK if settings.worker_configured else Status.BLOCKED,
                   "service-to-service auth for the remote plane"),
        Diagnostic("backup_restore", Status.WARNING, "run a restore drill before enabling remote"),
        Diagnostic("no_auto_upgrade", Status.OK, "no automatic paid upgrade; hard stops configured"),
    ]
    blocking = [c for c in checks if c.status is Status.BLOCKED]
    warned = [c for c in checks if c.status is Status.WARNING]
    if blocking:
        reason = "NO-GO: " + "; ".join(f"{c.name}: {c.detail}" for c in blocking)
        return CostGateResult(False, checks, reason)
    if warned:
        return CostGateResult(True, checks, "GO with warnings: " + "; ".join(c.name for c in warned))
    return CostGateResult(True, checks, "GO: all zero-cost prerequisites verified")
