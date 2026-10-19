"""Health/overview metrics for the Overview and Reliability screens (FR-032, NFR-06).

Every value is derived from stored state or provider checks. In a first-run empty state the
caller shows next steps instead of numbers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from ...domain.enums import JobStatus, Platform
from ...domain.scheduling import MIN_READY_DAYS, WARN_READY_DAYS, longest_consecutive_ready_days
from ...infrastructure.persistence.local_sqlite import Repository
from .notifications import digest_is_stale
from .preflight import HEARTBEAT_STALE_MINUTES
from .token_lifecycle import ALERT_DAYS_BEFORE_EXPIRY, assess_token_health


@dataclass
class Overview:
    has_data: bool = False
    can_publish: bool = False
    can_publish_reason: str = ""
    mode: str = "local"
    next_post_id: str = ""
    next_post_local: str = ""
    next_post_timezone: str = ""
    active_window_end: str = ""
    posts_in_window: int = 0
    buffer_days: int = 0
    buffer_status: str = "unknown"
    facebook_state: str = "Not configured"
    instagram_state: str = "Not configured"
    heartbeat_age_minutes: int | None = None
    heartbeat_ok: bool = False
    open_incidents: int = 0
    unknown_outcomes: int = 0
    latest_backup_at: str = ""
    last_restore_drill_at: str = ""
    digest_ok: bool = False
    token_warnings: list[str] = field(default_factory=list)
    job_counts: dict[str, int] = field(default_factory=dict)


def _heartbeat_age(repo: Repository, now: datetime) -> int | None:
    beat = repo.get_flag("scheduler_heartbeat_at") or repo.get_flag("worker_heartbeat_at")
    if not beat:
        return None
    try:
        last = datetime.fromisoformat(beat.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int((now - last).total_seconds() / 60)


def build_overview(repo: Repository, *, mode: str = "local", now: datetime | None = None) -> Overview:
    now = now or datetime.now(UTC)
    overview = Overview(mode=mode)

    counts = repo.count_jobs_by_status()
    overview.job_counts = counts
    overview.unknown_outcomes = counts.get(JobStatus.UNKNOWN_OUTCOME.value, 0)
    overview.open_incidents = len([i for i in repo.list_incidents() if i.state.value == "open"])
    overview.has_data = bool(counts) or bool(repo.list_assets())

    assets = repo.list_assets()
    ordered = [a.image_id for a in sorted(assets, key=lambda a: a.image_id)]
    overview.buffer_days = longest_consecutive_ready_days(repo.ready_synced_image_ids(), ordered)
    if overview.buffer_days >= WARN_READY_DAYS:
        overview.buffer_status = "healthy"
    elif overview.buffer_days >= MIN_READY_DAYS:
        overview.buffer_status = "warning"
    else:
        overview.buffer_status = "blocked"

    nxt = repo.next_due_job(now)
    if nxt:
        overview.next_post_id = nxt.post_id
        overview.next_post_local = nxt.scheduled_at
        overview.next_post_timezone = nxt.timezone

    queued = repo.list_jobs(statuses=[JobStatus.QUEUED])
    overview.posts_in_window = len(queued)

    overview.heartbeat_age_minutes = _heartbeat_age(repo, now)
    overview.heartbeat_ok = (
        overview.heartbeat_age_minutes is not None and overview.heartbeat_age_minutes <= HEARTBEAT_STALE_MINUTES
    )

    fb = repo.get_connection(Platform.FACEBOOK)
    ig = repo.get_connection(Platform.INSTAGRAM)
    overview.facebook_state = fb.activation_state.value if fb else "Not configured"
    overview.instagram_state = ig.activation_state.value if ig else "Not configured"

    backups = repo.list_backup_runs()
    if backups:
        overview.latest_backup_at = backups[0].created_at
        overview.last_restore_drill_at = backups[0].restore_drill_at

    overview.digest_ok = not digest_is_stale(repo, now)

    for conn in (fb, ig):
        if conn is None:
            continue
        health = assess_token_health(conn, now)
        if health.expired:
            overview.token_warnings.append(f"{conn.provider.label} token expired — reauthorize")
        elif health.needs_alert:
            overview.token_warnings.append(
                f"{conn.provider.label} token expires in {health.days_remaining} day(s) (T−{ALERT_DAYS_BEFORE_EXPIRY} alert)"
            )

    # Can publishing happen right now?
    if mode == "local":
        overview.can_publish = bool(queued) and not repo.is_paused(Platform.FACEBOOK) and not repo.is_paused(Platform.INSTAGRAM)
        overview.can_publish_reason = (
            "Local mode publishes only while this machine and the scheduler process are running."
            if overview.can_publish else "No queued jobs, or a platform is paused."
        )
    else:
        can = bool(queued) and overview.heartbeat_ok and overview.buffer_status != "blocked"
        overview.can_publish = can
        overview.can_publish_reason = (
            "Remote scheduler heartbeat is fresh and assets are buffered."
            if can else "Remote preconditions not met (heartbeat, buffer or queue)."
        )
    return overview


def last_restore_drill(repo: Repository) -> str:
    backups = repo.list_backup_runs()
    return backups[0].restore_drill_at if backups else ""
