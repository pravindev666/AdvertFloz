"""Safe re-import: field-level diff with published/in-flight locking (FR-010, PRD §6).

Matching is by stable ``post_id``, never row order. Published payloads and history are
immutable. In-flight/claimed jobs are locked until reconciled. Removed future rows require an
explicit cancellation confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.enums import JobStatus
from ...domain.models import Post
from ...infrastructure.persistence.local_sqlite import Repository

DIFF_FIELDS = (
    "image_id", "scheduled_at", "timezone", "platforms", "caption", "facebook_caption",
    "instagram_caption", "alt_text", "destination_url", "grace_minutes", "campaign_tag", "ai_disclosure_status",
)


@dataclass
class RowDiff:
    post_id: str
    changed_fields: dict[str, tuple[str, str]] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.changed_fields)


@dataclass
class ReimportPlan:
    new: list[Post] = field(default_factory=list)
    changed: list[RowDiff] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    locked: list[str] = field(default_factory=list)      # published or in-flight
    cancelled: list[str] = field(default_factory=list)   # present before, absent now
    warnings: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "new": len(self.new),
            "changed": len(self.changed),
            "unchanged": len(self.unchanged),
            "locked": len(self.locked),
            "cancelled": len(self.cancelled),
        }


def _field(post: Post, name: str) -> str:
    value = getattr(post, name)
    if name == "platforms":
        return ";".join(p.value for p in value)
    return str(value)


def diff_import(repo: Repository, campaign_id: str, revision_id: int, incoming: list[Post]) -> ReimportPlan:
    plan = ReimportPlan()
    existing = {p.post_id: p for p in repo.list_posts(campaign_id, revision_id)}
    jobs_by_post: dict[str, list] = {}
    for job in repo.list_jobs(campaign_id=campaign_id, revision_id=revision_id):
        jobs_by_post.setdefault(job.post_id, []).append(job)

    incoming_ids = {p.post_id for p in incoming}
    for post in incoming:
        current = existing.get(post.post_id)
        if current is None:
            plan.new.append(post)
            continue
        jobs = jobs_by_post.get(post.post_id, [])
        if any(j.status is JobStatus.PUBLISHED or j.status.is_in_flight for j in jobs):
            locked_fields = {
                name: (_field(current, name), _field(post, name))
                for name in DIFF_FIELDS
                if _field(current, name) != _field(post, name)
            }
            if locked_fields:
                plan.locked.append(post.post_id)
                plan.warnings.append(f"{post.post_id} has changed fields but is published/in-flight; locked until reconciled")
            else:
                plan.unchanged.append(post.post_id)
            continue

        changed = {
            name: (_field(current, name), _field(post, name))
            for name in DIFF_FIELDS
            if _field(current, name) != _field(post, name)
        }
        if changed:
            plan.changed.append(RowDiff(post.post_id, changed))
        else:
            plan.unchanged.append(post.post_id)

    for post_id in existing:
        if post_id not in incoming_ids:
            jobs = jobs_by_post.get(post_id, [])
            if any(j.status is JobStatus.PUBLISHED for j in jobs):
                plan.unchanged.append(post_id)
                plan.warnings.append(f"{post_id} is absent from the new plan but already published; history is preserved")
            else:
                plan.cancelled.append(post_id)

    return plan


def apply_reimport(
    repo: Repository,
    campaign_id: str,
    revision_id: int,
    incoming: list[Post],
    plan: ReimportPlan,
    *,
    confirm_cancellations: bool = False,
    actor: str = "operator",
) -> dict:
    """Apply new/changed rows. Never touches locked rows or published history."""
    if plan.cancelled and not confirm_cancellations:
        raise ValueError("cancellations require explicit confirmation")

    for post in plan.new:
        repo.upsert_post(post)
    changed_ids = {d.post_id for d in plan.changed}
    for post in incoming:
        if post.post_id in changed_ids:
            repo.upsert_post(post)
    for post_id in plan.cancelled:
        for job in repo.list_jobs(campaign_id=campaign_id, revision_id=revision_id, post_id=post_id):
            if not job.status.is_in_flight and job.status is not JobStatus.PUBLISHED:
                repo.transition_job(job.job_id, JobStatus.CANCELLED, clear_lease=True)
        repo.audit(actor, "reimport.cancel", post_id, "future row cancelled")

    repo.audit(actor, "reimport.apply", f"{campaign_id}@{revision_id}", str(plan.counts()))
    return plan.counts()
