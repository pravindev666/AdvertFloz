"""Reporting and export (FR-027, PRD §4.13).

All exports are derived from stored outcomes. Performance metrics (impressions, reach,
clicks) are never invented here — they appear only when imported from a real supported source.
"""
from __future__ import annotations

import csv
import io

from ...domain.enums import JobStatus, Platform
from ...domain.utm import build_utm
from ...infrastructure.persistence.local_sqlite import Repository

WHAT_POSTED_COLUMNS = [
    "post_id", "platform", "scheduled_at", "actual_at", "status", "remote_post_id", "permalink",
    "campaign_tag", "destination_url", "error_category",
]


def what_actually_posted_csv(repo: Repository) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=WHAT_POSTED_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for job in repo.list_jobs():
        post = repo.get_post(job.campaign_id, job.revision_id, job.post_id)
        writer.writerow(
            {
                "post_id": job.post_id,
                "platform": job.platform.value,
                "scheduled_at": job.scheduled_at,
                "actual_at": job.updated_at if job.status is JobStatus.PUBLISHED else "",
                "status": job.status.value,
                "remote_post_id": job.remote_post_id,
                "permalink": job.permalink,
                "campaign_tag": post.campaign_tag if post else "",
                "destination_url": post.destination_url if post else "",
                "error_category": job.last_error_class.value,
            }
        )
    return buffer.getvalue()


def _csv_for_statuses(repo: Repository, statuses: list[JobStatus]) -> str:
    buffer = io.StringIO(newline="")
    columns = ["post_id", "platform", "status", "scheduled_at", "attempt_count",
               "error_category", "next_retry_at", "updated_at"]
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for job in repo.list_jobs(statuses=statuses):
        writer.writerow(
            {
                "post_id": job.post_id,
                "platform": job.platform.value,
                "status": job.status.value,
                "scheduled_at": job.scheduled_at,
                "attempt_count": job.attempt_count,
                "error_category": job.last_error_class.value,
                "next_retry_at": job.next_retry_at,
                "updated_at": job.updated_at,
            }
        )
    return buffer.getvalue()


def failed_jobs_csv(repo: Repository) -> str:
    return _csv_for_statuses(repo, [JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_PERMANENT])


def unknown_jobs_csv(repo: Repository) -> str:
    return _csv_for_statuses(repo, [JobStatus.UNKNOWN_OUTCOME])


def missed_jobs_csv(repo: Repository) -> str:
    return _csv_for_statuses(repo, [JobStatus.MISSED])


def audit_csv(repo: Repository) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["at", "actor", "action", "target", "detail"])
    for event in repo.list_audit():
        writer.writerow([event.at, event.actor, event.action, event.target, event.detail])
    return buffer.getvalue()


def utm_export_csv(repo: Repository, campaign_id: str, revision_id: int, source: str = "advertfloz", medium: str = "social") -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["post_id", "destination_url", "utm_url"])
    for post in repo.list_posts(campaign_id, revision_id):
        if not post.destination_url.startswith("https://"):
            continue
        try:
            utm = build_utm(post.destination_url, post.campaign_tag, post.post_id, source, medium)
        except ValueError:
            utm = ""
        writer.writerow([post.post_id, post.destination_url, utm])
    return buffer.getvalue()


def per_platform_success_counts(repo: Repository) -> dict[str, int]:
    counts = {Platform.FACEBOOK.value: 0, Platform.INSTAGRAM.value: 0}
    for job in repo.list_jobs(statuses=[JobStatus.PUBLISHED]):
        counts[job.platform.value] += 1
    return counts


# ---------------------------------------------------------------------------
# Meta Business Suite Planner CSV fallback
# ---------------------------------------------------------------------------

META_SUITE_COLUMNS = [
    "Date",
    "Time",
    "Message",
    "Link",
    "Image File Name",
    "Alt Text",
    "Platform",
    "Campaign Tag",
    "Post ID",
]


def meta_business_suite_csv(repo: Repository, campaign_id: str, revision_id: int) -> str:
    """Export a CSV formatted for Meta Business Suite's native bulk scheduler.

    This is a fallback for operators who cannot use the Graph API (credential
    issues, verification delays, etc.).  They can download this CSV and
    manually upload it to Meta Business Suite Planner for scheduling.

    The columns follow Meta's expected format: Date, Time, Message, Link,
    Image File Name, and additional AdvertFloz metadata.
    """
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=META_SUITE_COLUMNS, extrasaction="ignore")
    writer.writeheader()

    for post in repo.list_posts(campaign_id, revision_id):
        # Parse scheduled_at to split into date and time
        scheduled = post.scheduled_at or ""
        date_part = ""
        time_part = ""
        if "T" in scheduled:
            date_part, time_part = scheduled.split("T", 1)
        elif " " in scheduled:
            date_part, time_part = scheduled.split(" ", 1)
        else:
            date_part = scheduled

        # Use Facebook caption preferably, fallback to generic caption
        caption = post.facebook_caption or post.caption or ""

        for platform in post.platforms:
            if platform == Platform.INSTAGRAM:
                caption = post.instagram_caption or post.caption or ""

            writer.writerow({
                "Date": date_part,
                "Time": time_part,
                "Message": caption,
                "Link": post.destination_url,
                "Image File Name": f"{post.image_id}.jpg",
                "Alt Text": post.alt_text or "",
                "Platform": platform.value.title(),
                "Campaign Tag": post.campaign_tag or "",
                "Post ID": post.post_id,
            })

    return buffer.getvalue()
