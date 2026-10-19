"""Activation gate (FR-026, PRD §7.6).

Activation is explicit and per-platform. A campaign row is never activated automatically,
and no row without an approved+synced real image can be queued.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ...domain.enums import (
    ActivationState,
    DisclosureStatus,
    JobStatus,
    Platform,
    ProductionState,
    SyncState,
)
from ...domain.scheduling import (
    DEFAULT_ACTIVATION_WINDOW_DAYS,
    MIN_READY_DAYS,
    WARN_READY_DAYS,
    longest_consecutive_ready_days,
)
from ...infrastructure.persistence.local_sqlite import Repository


@dataclass
class ActivationReadiness:
    platform: Platform
    state: ActivationState
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ready_consecutive_days: int = 0
    window_start: str = ""
    window_end: str = ""

    @property
    def can_activate(self) -> bool:
        return not self.blockers

    @property
    def is_ready(self) -> bool:
        return self.state in {ActivationState.READY_FOR_LOCAL_PILOT, ActivationState.READY_FOR_REMOTE_CANARY}


def _window_posts(repo: Repository, campaign_id: str, revision_id: int, platform: Platform, start: str, end: str):
    posts = [p for p in repo.list_posts(campaign_id, revision_id) if platform in p.platforms]
    return [p for p in posts if start <= p.scheduled_at[:10] <= end]


def assess_readiness(
    repo: Repository,
    *,
    campaign_id: str,
    revision_id: int,
    platform: Platform,
    window_start: str,
    window_days: int,
    remote_mode: bool,
    alert_path_verified: bool = True,
    connection_test_passed: bool = False,
) -> ActivationReadiness:
    start = window_start
    try:
        end_dt = datetime.strptime(window_start, "%Y-%m-%d") + timedelta(days=window_days - 1)
        end = end_dt.strftime("%Y-%m-%d")
    except ValueError:
        return ActivationReadiness(platform, ActivationState.NEEDS_OPERATOR_ACTION, [f"invalid window start {window_start!r}"])

    result = ActivationReadiness(platform=platform, state=ActivationState.NEEDS_OPERATOR_ACTION, window_start=start, window_end=end)

    if window_days > DEFAULT_ACTIVATION_WINDOW_DAYS:
        result.blockers.append(
            f"Window is {window_days} days; the default maximum is {DEFAULT_ACTIVATION_WINDOW_DAYS}. "
            "Extend deliberately after reviewing assets and account status."
        )

    conn = repo.get_connection(platform)
    if conn is None or not conn.page_id and platform is Platform.FACEBOOK:
        result.blockers.append("No Facebook Page selected; connect and choose a target first.")
    if conn is None or not conn.account_id and platform is Platform.INSTAGRAM:
        result.blockers.append("No Instagram professional account discovered; connect and confirm the account first.")
    if not connection_test_passed:
        result.blockers.append("Connection/permission test has not passed for this platform.")

    if remote_mode:
        if not alert_path_verified:
            result.blockers.append("Alert delivery has not been verified; required before remote activation.")
        conn_ok = conn is not None and conn.state.value in {"test_passed", "target_selected"}
        if not conn_ok:
            result.blockers.append("Remote activation requires a validated remote connection.")

    window_posts = _window_posts(repo, campaign_id, revision_id, platform, start, end)
    if not window_posts:
        result.blockers.append("No posts fall inside the chosen activation window.")

    ready_images: set[int] = set()
    for post in window_posts:
        asset = repo.get_asset(post.image_id)
        if asset is None:
            result.blockers.append(f"{post.post_id}: image {post.image_id}.jpg is missing.")
            continue
        if not asset.approved or asset.production_state.order < ProductionState.APPROVED.order:
            result.blockers.append(f"{post.post_id}: image {post.image_id}.jpg is not approved.")
        if remote_mode and asset.sync_state is not SyncState.SYNCED:
            result.blockers.append(f"{post.post_id}: image {post.image_id}.jpg is not synced remotely.")
        if post.ai_disclosure_status is DisclosureStatus.REQUIRED_PENDING:
            result.blockers.append(f"{post.post_id}: AI disclosure is required but pending review.")
        if asset.approved and (not remote_mode or asset.sync_state is SyncState.SYNCED):
            ready_images.add(post.image_id)

    ordered_ids = [p.image_id for p in sorted(window_posts, key=lambda p: p.scheduled_at)]
    days = longest_consecutive_ready_days(ready_images, ordered_ids)
    result.ready_consecutive_days = days
    if days < MIN_READY_DAYS:
        result.blockers.append(
            f"Only {days} consecutive approved day(s); at least {MIN_READY_DAYS} are required before normal activation."
        )
    elif days < WARN_READY_DAYS:
        result.warnings.append(f"{days} consecutive days ready; below the {WARN_READY_DAYS}-day comfort buffer.")

    if result.blockers:
        result.state = ActivationState.BLOCKED
    elif remote_mode:
        result.state = ActivationState.READY_FOR_REMOTE_CANARY
    else:
        result.state = ActivationState.READY_FOR_LOCAL_PILOT
    return result


def activate_window(
    repo: Repository,
    *,
    campaign_id: str,
    revision_id: int,
    platform: Platform,
    window_start: str,
    window_days: int,
    confirmed_target_id: str,
    remote_mode: bool = False,
    alert_path_verified: bool = True,
    connection_test_passed: bool = False,
    actor: str = "operator",
) -> ActivationReadiness:
    """Queue the newly-enabled jobs for one platform after every gate passes."""
    readiness = assess_readiness(
        repo, campaign_id=campaign_id, revision_id=revision_id, platform=platform,
        window_start=window_start, window_days=window_days, remote_mode=remote_mode,
        alert_path_verified=alert_path_verified, connection_test_passed=connection_test_passed,
    )
    if not readiness.can_activate:
        return readiness

    conn = repo.get_connection(platform)
    target = (conn.page_id if platform is Platform.FACEBOOK else conn.account_id) if conn else ""
    if confirmed_target_id and confirmed_target_id != target:
        readiness.blockers.append("Confirmed target does not match the selected target; refusing to retarget.")
        readiness.state = ActivationState.BLOCKED
        return readiness

    for post in _window_posts(repo, campaign_id, revision_id, platform, readiness.window_start, readiness.window_end):
        repo.set_post_enabled(campaign_id, revision_id, post.post_id, True)
        for job in repo.list_jobs(campaign_id=campaign_id, revision_id=revision_id, post_id=post.post_id, platform=platform):
            if job.status in {JobStatus.DRAFT, JobStatus.VALIDATION_BLOCKED, JobStatus.READY_FOR_REVIEW, JobStatus.APPROVED}:
                repo.transition_job(job.job_id, JobStatus.QUEUED, clear_lease=True)
    repo.audit(actor, "activate", f"{campaign_id}@{revision_id}:{platform.value}",
               f"window {readiness.window_start}..{readiness.window_end}, target {target}")
    return readiness
