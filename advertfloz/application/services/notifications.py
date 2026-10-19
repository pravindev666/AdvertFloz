"""Alerting and the independent daily digest (FR-024).

The digest is emitted by the scheduler process, not the Streamlit UI, so a stale heartbeat or
a missing digest is a real, detectable incident rather than an assumption.
"""
from __future__ import annotations

from datetime import UTC, datetime

from ...domain.enums import Severity
from ...infrastructure.notifications.telegram import TelegramBot
from ...infrastructure.persistence.local_sqlite import Repository

DIGEST_MAX_AGE_HOURS = 26

ALERT_KINDS = (
    "publish_failed",
    "publish_missed",
    "unknown_outcome",
    "token_expiring",
    "stale_worker",
    "low_buffer",
    "preflight_failed",
    "backup_failed",
    "missing_digest",
)


def notify(repo: Repository, bot: TelegramBot, kind: str, message: str) -> tuple[bool, str]:
    prefix = {"publish_failed": "❌", "publish_missed": "⏰", "unknown_outcome": "❓"}.get(kind, "•")
    sent, detail = bot.send(f"{prefix} AdvertFloz [{kind}]\n{message}")
    health = repo.get_notification_health("telegram")
    health.configured = bot.config.configured
    health.last_test_at = datetime.now(UTC).isoformat(timespec="seconds")
    health.last_test_ok = sent
    health.detail = detail
    repo.upsert_notification_health(health)
    return sent, detail


def send_test_alert(repo: Repository, bot: TelegramBot) -> tuple[bool, str]:
    return notify(repo, bot, "test", "AdvertFloz test alert. If you received this, alerting works.")


def build_daily_digest(repo: Repository, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    counts = repo.count_jobs_by_status()
    unknown = counts.get("UNKNOWN_OUTCOME", 0)
    incidents = repo.list_incidents()
    open_incidents = [i for i in incidents if i.state.value == "open"]
    assets = repo.list_assets()
    ready = repo.ready_synced_image_ids()
    lines = [
        f"AdvertFloz daily digest — {now.date().isoformat()}",
        f"Published: {counts.get('PUBLISHED', 0)} | Queued: {counts.get('QUEUED', 0)} | "
        f"Failed(retryable): {counts.get('FAILED_RETRYABLE', 0)} | Permanent: {counts.get('FAILED_PERMANENT', 0)}",
        f"UNKNOWN_OUTCOME: {unknown} | Missed: {counts.get('MISSED', 0)} | Paused: {counts.get('PAUSED', 0)}",
        f"Open incidents: {len(open_incidents)}",
        f"Assets: {len(assets)} total, {len(ready)} approved+synced",
    ]
    backups = repo.list_backup_runs()
    if backups:
        lines.append(f"Latest backup: {backups[0].created_at} ({backups[0].path})")
    else:
        lines.append("Latest backup: none recorded")
    return "\n".join(lines)


def emit_digest(repo: Repository, bot: TelegramBot, now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now(UTC)
    digest = build_daily_digest(repo, now)
    sent, detail = bot.send(digest)
    health = repo.get_notification_health("telegram")
    health.configured = bot.config.configured
    health.last_digest_at = now.isoformat(timespec="seconds")
    health.detail = detail
    repo.upsert_notification_health(health)
    return sent, detail


def digest_is_stale(repo: Repository, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    health = repo.get_notification_health("telegram")
    if not health.last_digest_at:
        return True
    try:
        last = datetime.fromisoformat(health.last_digest_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (now - last).total_seconds() > DIGEST_MAX_AGE_HOURS * 3600


def severity_for(kind: str) -> Severity:
    return {
        "unknown_outcome": Severity.CRITICAL,
        "publish_failed": Severity.DANGER,
        "token_expiring": Severity.WARNING,
        "stale_worker": Severity.DANGER,
        "missing_digest": Severity.WARNING,
        "low_buffer": Severity.WARNING,
        "backup_failed": Severity.DANGER,
        "preflight_failed": Severity.DANGER,
        "publish_missed": Severity.WARNING,
    }.get(kind, Severity.INFO)
