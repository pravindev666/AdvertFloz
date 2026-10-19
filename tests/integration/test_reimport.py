"""Integration test: safe re-import with field diffs and published/in-flight locking (FR-010)."""
from __future__ import annotations

from advertfloz.application.services.reimport import apply_reimport, diff_import
from advertfloz.domain.enums import JobStatus, Platform
from advertfloz.domain.models import Post
from tests.builders import seed_campaign


def _post(post_id: str, image_id: int, caption: str) -> Post:
    return Post(
        post_id=post_id, campaign_id="c1", revision_id=1, image_id=image_id,
        scheduled_at="2027-01-01T09:00:00", timezone="Asia/Kolkata",
        platforms=(Platform.FACEBOOK,), caption=caption, campaign_tag="tag",
    )


def test_reimport_diff_classifies_rows(repo):
    seed_campaign(repo, post_ids=["P001", "P002", "P003"])
    incoming = [
        _post("P001", 1, "Caption for P001"),   # unchanged
        _post("P002", 2, "CHANGED caption"),    # changed
        _post("P004", 4, "A new post"),         # new
        # P003 absent -> cancelled
    ]
    plan = diff_import(repo, "c1", 1, incoming)
    counts = plan.counts()
    assert counts["new"] == 1
    assert counts["changed"] == 1
    assert counts["unchanged"] == 1
    assert counts["cancelled"] == 1
    assert plan.changed[0].post_id == "P002"
    assert "caption" in plan.changed[0].changed_fields


def test_published_rows_are_locked(repo):
    seed_campaign(repo, post_ids=["P001"])
    for job in repo.list_jobs():
        repo.transition_job(job.job_id, JobStatus.PUBLISHED, clear_lease=True)
    plan = diff_import(repo, "c1", 1, [_post("P001", 1, "different caption")])
    assert plan.locked == ["P001"]
    assert not plan.changed


def test_cancellation_requires_confirmation(repo):
    seed_campaign(repo, post_ids=["P001", "P002"])
    plan = diff_import(repo, "c1", 1, [_post("P001", 1, "Caption for P001")])
    assert plan.cancelled == ["P002"]
    try:
        apply_reimport(repo, "c1", 1, [_post("P001", 1, "Caption for P001")], plan)
        raise AssertionError("expected confirmation requirement")
    except ValueError:
        pass
    apply_reimport(repo, "c1", 1, [_post("P001", 1, "Caption for P001")], plan, confirm_cancellations=True)
    assert any(j.status is JobStatus.CANCELLED for j in repo.list_jobs(post_id="P002"))
