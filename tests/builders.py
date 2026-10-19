"""Builders that seed durable state for integration tests."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from advertfloz.domain.enums import (
    ActivationState,
    AuthFlow,
    ConnectionState,
    DisclosureStatus,
    JobStatus,
    Platform,
    ProductionState,
    SyncState,
)
from advertfloz.domain.idempotency import job_key
from advertfloz.domain.models import Campaign, Connection, MediaAsset, PlatformJob, Post
from advertfloz.infrastructure.persistence.local_sqlite import Repository
from tests.support import plan_row


def seed_campaign(
    repo: Repository,
    *,
    campaign_id: str = "c1",
    revision_id: int = 1,
    post_ids: list[str] | None = None,
    platforms: tuple[Platform, ...] = (Platform.FACEBOOK,),
    approved: bool = True,
    synced: bool = True,
    due_in_past: bool = True,
    schedule: str = "2027-01-01T09:00:00",
    status: JobStatus = JobStatus.QUEUED,
    campaign_tag: str = "tag",
) -> tuple[str, int]:
    post_ids = post_ids or ["P001", "P002"]
    repo.upsert_campaign(Campaign(
        campaign_id=campaign_id, name=campaign_id, campaign_tag=campaign_tag,
        default_timezone="Asia/Kolkata", start_date="2027-01-01", end_date="2027-02-01",
    ))
    repo.create_revision(campaign_id, f"hash-{revision_id}")

    now = datetime.now(UTC)
    due = (now - timedelta(minutes=5)).isoformat(timespec="seconds") if due_in_past else (now + timedelta(hours=1)).isoformat(timespec="seconds")

    for post_id in post_ids:
        image_id = int(post_id[1:])
        row = plan_row(post_id, scheduled_at=schedule, platforms=";".join(p.value for p in platforms), campaign_tag=campaign_tag)
        post = Post(
            post_id=post_id, campaign_id=campaign_id, revision_id=revision_id, image_id=image_id,
            scheduled_at=schedule, timezone="Asia/Kolkata", platforms=platforms,
            caption=row["caption"], campaign_tag=campaign_tag, ai_disclosure_status=DisclosureStatus.NOT_REVIEWED,
            enabled=True,
        )
        repo.upsert_post(post)
        repo.upsert_asset(MediaAsset(
            image_id=image_id, filename=f"{image_id}.jpg", sha256="a" * 64, byte_size=1000,
            width=64, height=80,
            production_state=ProductionState.APPROVED if approved else ProductionState.GENERATED,
            sync_state=SyncState.SYNCED if synced else SyncState.NOT_SYNCED, approved=approved,
        ))
        for platform in platforms:
            repo.ensure_job(PlatformJob(
                post_id=post_id, platform=platform, campaign_id=campaign_id, revision_id=revision_id,
                target_account_id="target-1", status=status, scheduled_at=schedule, timezone="Asia/Kolkata",
                due_at_utc=due, idempotency_key=job_key(campaign_id, revision_id, post_id, platform),
            ))
    return campaign_id, revision_id


def seed_connection(repo: Repository, platform: Platform, *, page_id: str = "page-1", account_id: str = "ig-1") -> None:
    repo.upsert_connection(Connection(
        provider=platform, auth_flow=AuthFlow.FACEBOOK_LOGIN, state=ConnectionState.TEST_PASSED,
        account_id=account_id, account_name="acct", page_id=page_id, page_name="Page",
        scopes=(), activation_state=ActivationState.READY_FOR_LOCAL_PILOT,
    ))
