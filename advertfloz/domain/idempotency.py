"""Stable idempotency keys for platform jobs.

The key format is part of the durable-state contract (PRD §9):
``campaign_id:revision:post_id:platform``. It must be stable across cron ticks so a
duplicate claim can never produce a duplicate publish.
"""
from __future__ import annotations

from .enums import Platform

SEPARATOR = ":"


def job_key(campaign_id: str, revision_id: int, post_id: str, platform: Platform | str) -> str:
    plat = platform.value if isinstance(platform, Platform) else str(platform)
    parts = [str(campaign_id), str(revision_id), str(post_id), plat]
    for part in parts:
        if SEPARATOR in part:
            raise ValueError(f"idempotency key components may not contain {SEPARATOR!r}: {part!r}")
    return SEPARATOR.join(parts)


def job_identity(campaign_id: str, revision_id: int, post_id: str, platform: Platform | str) -> tuple[str, int, str, str]:
    """Tuple form used by the UNIQUE constraint on platform_jobs."""
    plat = platform.value if isinstance(platform, Platform) else str(platform)
    return (str(campaign_id), int(revision_id), str(post_id), plat)
