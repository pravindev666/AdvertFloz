"""Publishing orchestrator (FR-018, FR-019, FR-020, FR-021).

One bounded tick: release stale leases, claim a small set of due jobs atomically, then for
each job run the pre-send checks and either dispatch, defer (backoff), mark MISSED, or record
UNKNOWN_OUTCOME. Nothing loops or sleeps; the Instagram state machine advances one stage per
tick and persists progress.
"""
from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from ...domain.enums import ErrorClass, JobStatus, Platform, ProductionState, Severity
from ...domain.models import Incident, PlatformJob, PublishAttempt
from ...domain.scheduling import is_missed
from ...infrastructure.meta import facebook_pages, instagram_publish
from ...infrastructure.meta.graph_client import GraphClient
from ...infrastructure.meta.instagram_publish import InstagramStage
from ...infrastructure.meta.mock_provider import TransportTimeout
from ...infrastructure.persistence.local_sqlite import Repository

CLAIMABLE = [JobStatus.QUEUED, JobStatus.PROCESSING_MEDIA]
BASE_BACKOFF_SECONDS = 60
MAX_BACKOFF_SECONDS = 3600
IG_STAGE_DELAY_SECONDS = 30


@dataclass
class PublishContext:
    """Everything the orchestrator needs, injected so tests can supply mocks."""

    graph: GraphClient
    token_for: Callable[[Platform], str | None]
    media_url_for: Callable[[int], str | None]
    target_for: Callable[[Platform], str]
    now: datetime
    owner: str = "local-scheduler"

    def iso(self, dt: datetime) -> str:
        return dt.astimezone(UTC).isoformat(timespec="seconds")


@dataclass
class TickResult:
    claimed: int = 0
    published: int = 0
    deferred: int = 0
    missed: int = 0
    unknown: int = 0
    failed_permanent: int = 0
    paused_skipped: int = 0
    details: list[str] = field(default_factory=list)

    def account(self, outcome: str) -> None:
        if outcome == "unknown":
            self.unknown += 1
        elif outcome == "failed_permanent":
            self.failed_permanent += 1
        elif outcome == "deferred":
            self.deferred += 1
        else:
            self.details.append(outcome)


def _backoff_seconds(attempt: int, hint: int | None = None) -> int:
    if hint:
        return max(1, min(hint, MAX_BACKOFF_SECONDS))
    delay = min(BASE_BACKOFF_SECONDS * (2 ** max(0, attempt - 1)), MAX_BACKOFF_SECONDS)
    return int(delay * (0.75 + random.random() * 0.5))  # jitter


def _retry_at(ctx: PublishContext, attempt: int, hint: int | None = None) -> str:
    return ctx.iso(ctx.now + timedelta(seconds=_backoff_seconds(attempt, hint)))


def _incident(repo: Repository, *, incident_id: str, severity: Severity, cause: str, platform: Platform, post_id: str,
              diagnosis: str, remediation: str, retry_eligible: bool) -> None:
    repo.add_incident(
        Incident(
            incident_id=incident_id, severity=severity, cause=cause, platform=platform, post_id=post_id,
            diagnosis=diagnosis, remediation=remediation, retry_eligible=retry_eligible,
        )
    )


def apply_error(repo: Repository, job: PlatformJob, ctx: PublishContext, error_class: ErrorClass,
                summary: str, correlation_id: str) -> str:
    """Map a classified error to a durable job transition. Returns an outcome label."""
    repo.record_attempt(
        PublishAttempt(job.post_id, job.platform, job.last_stage or "dispatch", correlation_id,
                       response_summary=summary, error_class=error_class, retry_decision=error_class.value),
        job_id=job.job_id,
    )
    if error_class is ErrorClass.AUTH:
        repo.transition_job(job.job_id, JobStatus.PAUSED, clear_lease=True, last_error_class=error_class)
        repo.pause(job.platform.value, actor="system")
        _incident(repo, incident_id=f"auth-{job.job_id}", severity=Severity.CRITICAL, cause="authorization",
                  platform=job.platform, post_id=job.post_id, diagnosis=summary,
                  remediation="Reconnect the platform and re-authorize; then resume.", retry_eligible=False)
        return "auth_paused"
    if error_class is ErrorClass.RESTRICTION:
        repo.transition_job(job.job_id, JobStatus.PAUSED, clear_lease=True, last_error_class=error_class)
        repo.pause(job.platform.value, actor="system")
        _incident(repo, incident_id=f"restriction-{job.job_id}", severity=Severity.CRITICAL, cause="account_restriction",
                  platform=job.platform, post_id=job.post_id, diagnosis=summary,
                  remediation="Review the account in Meta; resolve any policy issue before resuming.", retry_eligible=False)
        return "restricted_paused"
    if error_class is ErrorClass.PAYLOAD:
        repo.transition_job(job.job_id, JobStatus.FAILED_PERMANENT, clear_lease=True, last_error_class=error_class)
        _incident(repo, incident_id=f"payload-{job.job_id}", severity=Severity.DANGER, cause="invalid_payload",
                  platform=job.platform, post_id=job.post_id, diagnosis=summary,
                  remediation="Fix the caption/media and re-import; this row will not be retried automatically.",
                  retry_eligible=False)
        return "failed_permanent"
    if error_class is ErrorClass.AMBIGUOUS:
        repo.transition_job(job.job_id, JobStatus.UNKNOWN_OUTCOME, clear_lease=True, last_error_class=error_class)
        _incident(repo, incident_id=f"unknown-{job.job_id}", severity=Severity.CRITICAL, cause="unknown_outcome",
                  platform=job.platform, post_id=job.post_id, diagnosis=summary,
                  remediation="Check the provider (Page/IG) for this post before any retry. Do not blind retry.",
                  retry_eligible=True)
        return "unknown"
    # RATE_LIMIT / TRANSIENT / UNKNOWN → bounded backoff retry
    repo.transition_job(job.job_id, JobStatus.FAILED_RETRYABLE, clear_lease=True, last_error_class=error_class,
                        next_retry_at=_retry_at(ctx, job.attempt_count + 1))
    return "deferred"


def _dispatch_facebook(repo: Repository, job: PlatformJob, post, ctx: PublishContext, result: TickResult) -> None:
    token = ctx.token_for(Platform.FACEBOOK)
    target = ctx.target_for(Platform.FACEBOOK)
    url = ctx.media_url_for(post.image_id)
    if not token or not target or not url:
        result.account(apply_error(repo, job, ctx, ErrorClass.AUTH, "missing page token/target/media URL", "precondition"))
        return
    caption = post.effective_caption(Platform.FACEBOOK)
    try:
        outcome = facebook_pages.publish_photo(ctx.graph, target, token, url, caption)
    except TransportTimeout:
        result.account(apply_error(repo, job, ctx, ErrorClass.TRANSIENT, "connection timed out before send", "transport"))
        return
    if outcome.ok:
        repo.transition_job(job.job_id, JobStatus.PUBLISHED, clear_lease=True, remote_post_id=outcome.remote_id,
                            permalink=outcome.permalink, increment_attempt=True)
        repo.record_attempt(PublishAttempt(job.post_id, job.platform, "publish", "fb",
                                           response_summary=outcome.summary, retry_decision="done"), job_id=job.job_id)
        _mark_asset_ready(repo, post.image_id)
        result.published += 1
        return
    result.account(apply_error(repo, job, ctx, outcome.error_class or ErrorClass.UNKNOWN, outcome.summary, "fb-publish"))


def _dispatch_instagram(repo: Repository, job: PlatformJob, post, ctx: PublishContext, result: TickResult) -> None:
    token = ctx.token_for(Platform.INSTAGRAM)
    ig_user = ctx.target_for(Platform.INSTAGRAM)
    if not token or not ig_user:
        result.account(apply_error(repo, job, ctx, ErrorClass.AUTH, "missing IG token/target", "precondition"))
        return
    stage = InstagramStage(job.last_stage) if job.last_stage else InstagramStage.CREATE_CONTAINER
    caption = post.effective_caption(Platform.INSTAGRAM)

    if stage is InstagramStage.CREATE_CONTAINER:
        url = ctx.media_url_for(post.image_id)
        if not url:
            result.account(apply_error(repo, job, ctx, ErrorClass.PAYLOAD, "no media URL", "create_container"))
            return
        container = instagram_publish.create_container(ctx.graph, ig_user, token, url, caption)
        if not container.ok:
            result.account(apply_error(repo, job, ctx, container.error_class or ErrorClass.UNKNOWN, container.summary, "ig-container"))
            return
        repo.set_container_id(job.job_id, container.container_id)
        repo.transition_job(job.job_id, JobStatus.PROCESSING_MEDIA, clear_lease=True,
                            last_stage=InstagramStage.CHECK_STATUS.value, increment_attempt=True,
                            next_retry_at=ctx.iso(ctx.now + timedelta(seconds=IG_STAGE_DELAY_SECONDS)))
        result.deferred += 1
        return

    if stage is InstagramStage.CHECK_STATUS:
        if not job.container_id:
            repo.transition_job(job.job_id, JobStatus.PROCESSING_MEDIA, clear_lease=True,
                                last_stage=InstagramStage.CREATE_CONTAINER.value)
            result.deferred += 1
            return
        status = instagram_publish.check_status(ctx.graph, job.container_id, token)
        if not status.ok:
            result.account(apply_error(repo, job, ctx, status.error_class or ErrorClass.UNKNOWN, status.summary, "ig-status"))
            return
        nxt = instagram_publish.next_stage(InstagramStage.CHECK_STATUS, status.status)
        repo.transition_job(job.job_id, JobStatus.PROCESSING_MEDIA, clear_lease=True, last_stage=nxt.value,
                            next_retry_at=ctx.iso(ctx.now + timedelta(seconds=IG_STAGE_DELAY_SECONDS)))
        result.deferred += 1
        return

    # PUBLISH
    try:
        outcome = instagram_publish.publish_container(ctx.graph, ig_user, token, job.container_id)
    except TransportTimeout:
        result.account(apply_error(repo, job, ctx, ErrorClass.AMBIGUOUS, "timeout after container may have published", "ig-publish"))
        return
    if outcome.ok:
        repo.transition_job(job.job_id, JobStatus.PUBLISHED, clear_lease=True, remote_post_id=outcome.media_id,
                            permalink=outcome.permalink, last_stage=InstagramStage.DONE.value, increment_attempt=True)
        repo.record_attempt(PublishAttempt(job.post_id, job.platform, "publish", "ig",
                                           response_summary=outcome.summary, retry_decision="done"), job_id=job.job_id)
        _mark_asset_ready(repo, post.image_id)
        result.published += 1
        return
    result.account(apply_error(repo, job, ctx, outcome.error_class or ErrorClass.UNKNOWN, outcome.summary, "ig-publish"))


def _mark_asset_ready(repo: Repository, image_id: int) -> None:
    asset = repo.get_asset(image_id)
    if asset is not None and asset.production_state.order >= ProductionState.APPROVED.order:
        repo.update_production_state(image_id, ProductionState.READY)


def _precondition(repo: Repository, job: PlatformJob, post) -> str | None:
    asset = repo.get_asset(post.image_id)
    if asset is None or not asset.approved:
        return f"image {post.image_id}.jpg is missing or not approved"
    return None


def run_tick(repo: Repository, ctx: PublishContext, *, limit: int = 5, lease_seconds: int = 300) -> TickResult:
    result = TickResult()
    repo.release_expired_leases(ctx.now)
    jobs = repo.claim_due_jobs(CLAIMABLE, ctx.now, limit, ctx.owner, lease_seconds)
    result.claimed = len(jobs)
    for job in jobs:
        post = repo.get_post(job.campaign_id, job.revision_id, job.post_id)
        if post is None:
            repo.transition_job(job.job_id, JobStatus.FAILED_PERMANENT, clear_lease=True, last_error_class=ErrorClass.PAYLOAD)
            result.failed_permanent += 1
            continue
        if repo.is_paused(job.platform):
            repo.transition_job(job.job_id, JobStatus.QUEUED, clear_lease=True)
            result.paused_skipped += 1
            continue
        if is_missed(post.scheduled_at, post.timezone, ctx.now, post.grace_minutes):
            repo.transition_job(job.job_id, JobStatus.MISSED, clear_lease=True, last_error_class=ErrorClass.UNKNOWN)
            _incident(repo, incident_id=f"missed-{job.job_id}", severity=Severity.WARNING, cause="missed_window",
                      platform=job.platform, post_id=job.post_id,
                      diagnosis="Scheduled time passed beyond the grace window.",
                      remediation="Choose explicitly whether to reschedule or cancel; never publish silently late.",
                      retry_eligible=False)
            result.missed += 1
            continue
        blocker = _precondition(repo, job, post)
        if blocker:
            repo.transition_job(job.job_id, JobStatus.VALIDATION_BLOCKED, clear_lease=True, last_error_class=ErrorClass.PAYLOAD)
            result.failed_permanent += 1
            continue
        if job.platform is Platform.FACEBOOK:
            _dispatch_facebook(repo, job, post, ctx, result)
        else:
            _dispatch_instagram(repo, job, post, ctx, result)
    return result
