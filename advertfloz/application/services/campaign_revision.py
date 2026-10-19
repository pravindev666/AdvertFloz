"""Campaign revision assembly and commit (FR-005, FR-010, PRD §6).

Turns a validated :class:`ImportResult` into durable state: campaign, immutable revision,
posts, media assets and per-platform jobs. Import never activates anything — jobs are
created in ``DRAFT``/``VALIDATION_BLOCKED`` only.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from ...domain.enums import (
    ActivationState,
    JobStatus,
    Platform,
    ProductionState,
    SyncState,
)
from ...domain.idempotency import job_key
from ...domain.models import Campaign, MediaAsset, PlatformJob
from ...domain.scheduling import to_utc
from ...infrastructure.persistence.local_sqlite import Repository
from .campaign_import import ImportResult


def manifest_hash(result: ImportResult) -> str:
    payload = {
        "plan_hash": result.plan_hash,
        "campaign_id": result.campaign_id,
        "posts": [p.post_id for p in result.posts],
        "images": sorted(result.assets.keys()),
        "assets": {str(k): v.sha256 for k, v in sorted(result.assets.items())},
    }
    import hashlib

    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _due_utc(post) -> str:
    dt = to_utc(post.scheduled_at, post.timezone)
    return dt.isoformat(timespec="seconds") if dt else ""


def commit_import(
    repo: Repository,
    result: ImportResult,
    *,
    campaign_name: str | None = None,
    target_account_ids: dict[Platform, str] | None = None,
    created_by: str = "operator",
) -> int:
    """Persist an import as a new immutable campaign revision. Returns the revision id.

    Requires ``result.ok`` (no blocking errors); raises ValueError otherwise so an incomplete
    import can never be committed.
    """
    if not result.ok:
        raise ValueError("cannot commit an import with blocking errors")

    target_account_ids = target_account_ids or {}
    campaign = Campaign(
        campaign_id=result.campaign_id,
        name=campaign_name or result.campaign_name or result.campaign_id,
        campaign_tag=result.campaign_tag,
        default_timezone=result.default_timezone or "Asia/Kolkata",
        start_date=result.start_date,
        end_date=result.end_date,
    )
    repo.upsert_campaign(campaign)
    revision_id = repo.create_revision(result.campaign_id, manifest_hash(result), created_by=created_by)

    asset_ids_in_zip = set(result.assets)
    for post in result.posts:
        repo.upsert_post(post)
        asset = repo.get_asset(post.image_id)
        if post.image_id in asset_ids_in_zip and asset is None:
            info = result.assets[post.image_id]
            repo.upsert_asset(
                MediaAsset(
                    image_id=post.image_id,
                    filename=info.filename,
                    sha256=info.sha256,
                    byte_size=info.byte_size,
                    width=info.width,
                    height=info.height,
                    production_state=ProductionState.UPLOADED,
                    sync_state=SyncState.NOT_SYNCED,
                    approved=False,
                    zip_part=info.filename,
                )
            )
        for platform in post.platforms:
            repo.ensure_job(
                PlatformJob(
                    post_id=post.post_id,
                    platform=platform,
                    campaign_id=post.campaign_id,
                    revision_id=revision_id,
                    target_account_id=target_account_ids.get(platform, ""),
                    status=JobStatus.DRAFT,
                    scheduled_at=post.scheduled_at,
                    timezone=post.timezone,
                    due_at_utc=_due_utc(post),
                    idempotency_key=job_key(post.campaign_id, revision_id, post.post_id, platform),
                )
            )

    repo.audit(created_by, "import.commit", f"{result.campaign_id}@{revision_id}", f"{len(result.posts)} posts, {len(result.assets)} images")
    return revision_id


def revision_summary(repo: Repository, campaign_id: str, revision_id: int) -> dict:
    posts = repo.list_posts(campaign_id, revision_id)
    jobs = repo.list_jobs(campaign_id=campaign_id, revision_id=revision_id)
    return {
        "posts": len(posts),
        "jobs": len(jobs),
        "facebook_jobs": sum(1 for j in jobs if j.platform is Platform.FACEBOOK),
        "instagram_jobs": sum(1 for j in jobs if j.platform is Platform.INSTAGRAM),
        "enabled_posts": sum(1 for p in posts if p.enabled),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def activation_state_for(ready_days: int, connected: bool, has_target: bool) -> ActivationState:
    if not connected:
        return ActivationState.NOT_CONFIGURED
    if not has_target:
        return ActivationState.NEEDS_OPERATOR_ACTION
    if ready_days < 14:
        return ActivationState.BLOCKED
    return ActivationState.READY_FOR_LOCAL_PILOT
