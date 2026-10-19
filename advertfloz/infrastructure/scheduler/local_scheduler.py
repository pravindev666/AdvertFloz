"""Local bounded scheduler (NFR-04).

Streamlit is never the scheduler of record. This module is driven by ``scheduler_cli`` (or
``python -m advertfloz.scheduler_cli tick``), which can be invoked by Windows Task Scheduler
or cron. Each invocation performs one bounded tick and persists progress.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ...application.services import incidents as incidents_service
from ...application.services.notifications import emit_digest
from ...application.services.publish_orchestrator import PublishContext, TickResult, run_tick
from ...config import Settings
from ...domain.enums import JobStatus, Platform
from ..meta.graph_client import HttpGraphClient
from ..meta.mock_provider import MockGraphClient
from ..meta.token_store import load_token
from ..notifications.telegram import TelegramBot, TelegramConfig
from ..persistence.local_sqlite import Repository
from ..security.crypto import TokenCipher

HEARTBEAT_KEY = "scheduler_heartbeat_at"


@dataclass
class SchedulerRun:
    tick: TickResult
    heartbeat_at: str
    incidents: list
    digest_sent: bool


def _cipher(settings: Settings) -> TokenCipher:
    key = settings.secret("TOKEN_ENCRYPTION_KEY")
    if not key:
        return TokenCipher()
    return TokenCipher.single(key, settings.token_encryption_key_id)


def _graph(settings: Settings):
    if settings.mode == "demo":
        return MockGraphClient()
    return HttpGraphClient(version=settings.meta_graph_version)


def _media_url_factory(settings: Settings):
    if settings.mode == "demo":
        return lambda image_id: f"https://demo.invalid/media/{image_id}.jpg"
    if settings.media_base_url:
        base = settings.media_base_url.rstrip("/")
        return lambda image_id: f"{base}/{image_id}.jpg"
    return lambda image_id: None


def build_context(repo: Repository, settings: Settings, now: datetime | None = None) -> PublishContext:
    cipher = _cipher(settings)
    now = now or datetime.now(UTC)

    tokens = {p: load_token(repo, cipher, p) for p in (Platform.FACEBOOK, Platform.INSTAGRAM)}
    if settings.mode == "demo":
        tokens = {Platform.FACEBOOK: "demo-token", Platform.INSTAGRAM: "demo-token"}

    def token_for(platform: Platform) -> str | None:
        return tokens.get(platform)

    def target_for(platform: Platform) -> str:
        conn = repo.get_connection(platform)
        if conn is None:
            return ""
        return conn.page_id if platform is Platform.FACEBOOK else conn.account_id

    return PublishContext(
        graph=_graph(settings),
        token_for=token_for,
        media_url_for=_media_url_factory(settings),
        target_for=target_for,
        now=now,
        owner="local-scheduler",
    )


def run_once(
    repo: Repository,
    settings: Settings,
    *,
    limit: int = 5,
    lease_seconds: int = 300,
    now: datetime | None = None,
    emit_daily_digest: bool = False,
) -> SchedulerRun:
    now = now or datetime.now(UTC)
    ctx = build_context(repo, settings, now)
    tick = run_tick(repo, ctx, limit=limit, lease_seconds=lease_seconds)

    heartbeat = now.isoformat(timespec="seconds")
    repo.set_flag(HEARTBEAT_KEY, heartbeat)

    raised = incidents_service.detect_health_incidents(repo, now=now, remote_mode=settings.mode == "remote")

    digest_sent = False
    if emit_daily_digest:
        bot = TelegramBot(TelegramConfig(settings.secret("TELEGRAM_BOT_TOKEN"), settings.telegram_allowed_chat_id,
                                         settings.secret("TELEGRAM_WEBHOOK_SECRET")))
        digest_sent, _ = emit_digest(repo, bot, now)

    # Retry sweeper: move FAILED_RETRYABLE jobs whose backoff elapsed back to QUEUED.
    for job in repo.list_jobs(statuses=[JobStatus.FAILED_RETRYABLE]):
        if not job.next_retry_at:
            repo.transition_job(job.job_id, JobStatus.QUEUED, clear_lease=True)
        else:
            try:
                due = datetime.fromisoformat(job.next_retry_at.replace("Z", "+00:00"))
            except ValueError:
                due = now
            if due <= now:
                repo.transition_job(job.job_id, JobStatus.QUEUED, clear_lease=True)

    return SchedulerRun(tick=tick, heartbeat_at=heartbeat, incidents=raised, digest_sent=digest_sent)


def heartbeat_stale(repo: Repository, now: datetime | None = None, max_minutes: int = 150) -> bool:
    now = now or datetime.now(UTC)
    beat = repo.get_flag(HEARTBEAT_KEY)
    if not beat:
        return True
    try:
        return (now - datetime.fromisoformat(beat.replace("Z", "+00:00"))) > timedelta(minutes=max_minutes)
    except ValueError:
        return True
