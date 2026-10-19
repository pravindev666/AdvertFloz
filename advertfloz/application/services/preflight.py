"""T-24h preflight over the next 48 hours (FR-023).

Checks credentials, permissions, media URLs, asset checksums, quota, system clock, worker
heartbeat, active window, image buffer, notification delivery and backup health. Each check
reports OK / WARNING / BLOCKED with a safe, non-secret detail.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

from ...domain.enums import JobStatus, Platform, SyncState
from ...domain.scheduling import MIN_READY_DAYS, longest_consecutive_ready_days
from ...infrastructure.persistence.local_sqlite import Repository
from .notifications import digest_is_stale

HEARTBEAT_STALE_MINUTES = 150  # ~2.5 hours, tolerant of Cron jitter


class Check(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


@dataclass
class CheckResult:
    name: str
    status: Check
    detail: str


@dataclass
class PreflightReport:
    window_start: str
    window_end: str
    jobs_in_window: int
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def blocked(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status is Check.BLOCKED]

    @property
    def ok(self) -> bool:
        return not self.blocked


def _heartbeat(repo: Repository) -> str:
    return repo.get_flag("scheduler_heartbeat_at") or repo.get_flag("worker_heartbeat_at")


def run_preflight(
    repo: Repository,
    *,
    now: datetime | None = None,
    hours: int = 48,
    remote_mode: bool = False,
    media_url_for=None,
    clock_skew_seconds: float = 0.0,
) -> PreflightReport:
    now = now or datetime.now(UTC)
    until = now + timedelta(hours=hours)
    report = PreflightReport(window_start=now.isoformat(timespec="seconds"), window_end=until.isoformat(timespec="seconds"), jobs_in_window=0)

    def add(name: str, status: Check, detail: str) -> None:
        report.checks.append(CheckResult(name, status, detail))

    jobs = repo.jobs_due_between(now, until)
    report.jobs_in_window = len(jobs)

    # Credentials / permissions per platform present in the window.
    platforms = {j.platform for j in jobs}
    for platform in sorted(platforms, key=lambda p: p.value):
        conn = repo.get_connection(platform)
        if conn is None or not conn.account_id and platform is Platform.INSTAGRAM:
            add(f"connection:{platform.value}", Check.BLOCKED, "no connection/target for a platform with upcoming jobs")
        elif conn.state.value in {"reconnect_required", "restricted", "permission_missing"}:
            add(f"connection:{platform.value}", Check.BLOCKED, f"connection state {conn.state.value}")
        else:
            add(f"connection:{platform.value}", Check.OK, f"state {conn.state.value}")

    # Media URLs + checksums for upcoming jobs.
    missing_checksums = 0
    missing_urls = 0
    for job in jobs:
        post = repo.get_post(job.campaign_id, job.revision_id, job.post_id)
        if post is None:
            continue
        asset = repo.get_asset(post.image_id)
        if asset is None:
            missing_checksums += 1
            continue
        if not asset.sha256:
            missing_checksums += 1
        if media_url_for is not None and not media_url_for(post.image_id):
            missing_urls += 1
    if missing_checksums:
        add("assets:checksums", Check.BLOCKED, f"{missing_checksums} upcoming job(s) reference assets without verified checksums")
    else:
        add("assets:checksums", Check.OK, "all upcoming assets have checksums")
    if media_url_for is not None and missing_urls:
        add("media:urls", Check.BLOCKED, f"{missing_urls} upcoming job(s) have no retrievable media URL")
    elif media_url_for is not None:
        add("media:urls", Check.OK, "media URLs resolvable")

    # Remote-mode asset sync.
    if remote_mode:
        unsynced = 0
        for job in jobs:
            post = repo.get_post(job.campaign_id, job.revision_id, job.post_id)
            if post is None:
                continue
            asset = repo.get_asset(post.image_id)
            if asset is not None and asset.sync_state is not SyncState.SYNCED:
                unsynced += 1
        add("assets:remote_sync", Check.BLOCKED if unsynced else Check.OK,
            f"{unsynced} upcoming asset(s) not synced remotely" if unsynced else "all upcoming assets synced")

    # Image buffer.
    assets = repo.list_assets()
    ordered = [a.image_id for a in sorted(assets, key=lambda a: a.image_id)]
    ready = repo.ready_synced_image_ids()
    buffer_days = longest_consecutive_ready_days(ready, ordered)
    add("assets:buffer", Check.WARNING if buffer_days < MIN_READY_DAYS else Check.OK,
        f"{buffer_days} consecutive approved+synced day(s)")

    # Worker / scheduler heartbeat.
    beat = _heartbeat(repo)
    if not beat:
        add("heartbeat", Check.WARNING if not remote_mode else Check.BLOCKED, "no heartbeat recorded yet")
    else:
        try:
            age_min = (now - datetime.fromisoformat(beat.replace("Z", "+00:00"))).total_seconds() / 60
            status = Check.OK if age_min <= HEARTBEAT_STALE_MINUTES else Check.BLOCKED
            add("heartbeat", status, f"last tick {int(age_min)} min ago")
        except ValueError:
            add("heartbeat", Check.WARNING, "heartbeat timestamp unreadable")

    # Notification delivery + digest freshness.
    health = repo.get_notification_health("telegram")
    if health.configured and health.last_test_ok:
        add("alerts", Check.OK, "alert path verified")
    else:
        add("alerts", Check.WARNING, "alert path not yet verified with a test message")
    add("digest", Check.WARNING if digest_is_stale(repo, now) else Check.OK,
        "daily digest missing or stale" if digest_is_stale(repo, now) else "digest fresh")

    # Backup health.
    backups = repo.list_backup_runs()
    if not backups:
        add("backup", Check.WARNING, "no backup recorded yet")
    else:
        add("backup", Check.OK if backups[0].verified else Check.WARNING,
            f"latest backup {backups[0].created_at} verified={backups[0].verified}")

    # Clock sanity.
    add("clock", Check.OK if abs(clock_skew_seconds) < 300 else Check.WARNING,
        f"clock skew {int(clock_skew_seconds)}s")

    # Active window.
    queued = repo.list_jobs(statuses=[JobStatus.QUEUED])
    add("window", Check.OK if queued or jobs else Check.WARNING,
        f"{len(queued)} queued job(s) overall")

    return report
