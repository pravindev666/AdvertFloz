"""Integration test: the activation gate (FR-026)."""
from __future__ import annotations

from datetime import date, timedelta

from advertfloz.application.services.activation import activate_window, assess_readiness
from advertfloz.domain.enums import ActivationState, JobStatus, Platform, ProductionState, SyncState
from advertfloz.domain.idempotency import job_key
from advertfloz.domain.models import Campaign, MediaAsset, PlatformJob, Post
from advertfloz.infrastructure.persistence.local_sqlite import Repository
from tests.builders import seed_connection


def seed_days(repo: Repository, days: int, *, approved: bool = True, synced: bool = True) -> tuple[str, int]:
    repo.upsert_campaign(Campaign(campaign_id="c1", name="c1", campaign_tag="tag",
                                  default_timezone="Asia/Kolkata", start_date="2027-01-01", end_date="2027-03-01"))
    repo.create_revision("c1", "h1")
    start = date(2027, 1, 1)
    for index in range(days):
        day = start + timedelta(days=index)
        image_id = index + 1
        post_id = f"P{image_id:03d}"
        schedule = f"{day.isoformat()}T09:00:00"
        repo.upsert_post(Post(
            post_id=post_id, campaign_id="c1", revision_id=1, image_id=image_id,
            scheduled_at=schedule, timezone="Asia/Kolkata", platforms=(Platform.FACEBOOK,), caption="c",
        ))
        repo.upsert_asset(MediaAsset(
            image_id=image_id, filename=f"{image_id}.jpg", sha256="a" * 64, byte_size=100,
            production_state=ProductionState.APPROVED if approved else ProductionState.GENERATED,
            sync_state=SyncState.SYNCED if synced else SyncState.NOT_SYNCED, approved=approved,
        ))
        repo.ensure_job(PlatformJob(
            post_id=post_id, platform=Platform.FACEBOOK, campaign_id="c1", revision_id=1,
            target_account_id="page-1", status=JobStatus.DRAFT, scheduled_at=schedule, timezone="Asia/Kolkata",
            due_at_utc="", idempotency_key=job_key("c1", 1, post_id, Platform.FACEBOOK),
        ))
    seed_connection(repo, Platform.FACEBOOK)
    return "c1", 1


def test_14_day_buffer_ready_for_local_pilot(repo):
    seed_days(repo, 14)
    readiness = assess_readiness(
        repo, campaign_id="c1", revision_id=1, platform=Platform.FACEBOOK,
        window_start="2027-01-01", window_days=14, remote_mode=False, connection_test_passed=True,
    )
    assert readiness.can_activate, readiness.blockers
    assert readiness.state is ActivationState.READY_FOR_LOCAL_PILOT


def test_below_14_days_blocks_activation(repo):
    seed_days(repo, 10)
    readiness = assess_readiness(
        repo, campaign_id="c1", revision_id=1, platform=Platform.FACEBOOK,
        window_start="2027-01-01", window_days=10, remote_mode=False, connection_test_passed=True,
    )
    assert not readiness.can_activate
    assert any("14" in b for b in readiness.blockers)


def test_window_over_30_days_blocked(repo):
    seed_days(repo, 35)
    readiness = assess_readiness(
        repo, campaign_id="c1", revision_id=1, platform=Platform.FACEBOOK,
        window_start="2027-01-01", window_days=35, remote_mode=False, connection_test_passed=True,
    )
    assert any("30" in b for b in readiness.blockers)


def test_unapproved_asset_blocks(repo):
    seed_days(repo, 14, approved=False)
    readiness = assess_readiness(
        repo, campaign_id="c1", revision_id=1, platform=Platform.FACEBOOK,
        window_start="2027-01-01", window_days=14, remote_mode=False, connection_test_passed=True,
    )
    assert not readiness.can_activate


def test_remote_requires_sync_and_alerts(repo):
    seed_days(repo, 14, synced=False)
    readiness = assess_readiness(
        repo, campaign_id="c1", revision_id=1, platform=Platform.FACEBOOK,
        window_start="2027-01-01", window_days=14, remote_mode=True,
        connection_test_passed=True, alert_path_verified=False,
    )
    assert not readiness.can_activate
    assert any("synced" in b for b in readiness.blockers)
    assert any("Alert" in b for b in readiness.blockers)


def test_activate_queues_jobs_and_audits(repo):
    seed_days(repo, 14)
    readiness = activate_window(
        repo, campaign_id="c1", revision_id=1, platform=Platform.FACEBOOK,
        window_start="2027-01-01", window_days=14, confirmed_target_id="page-1", connection_test_passed=True,
    )
    assert readiness.can_activate
    assert all(j.status is JobStatus.QUEUED for j in repo.list_jobs())
    assert any(e.action == "activate" for e in repo.list_audit())


def test_target_mismatch_blocks(repo):
    seed_days(repo, 14)
    readiness = activate_window(
        repo, campaign_id="c1", revision_id=1, platform=Platform.FACEBOOK,
        window_start="2027-01-01", window_days=14, confirmed_target_id="OTHER", connection_test_passed=True,
    )
    assert any("target" in b.lower() for b in readiness.blockers)
