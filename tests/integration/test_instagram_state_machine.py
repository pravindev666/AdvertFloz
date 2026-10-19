"""Integration test: Instagram container state machine resumed across ticks (FR-019)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from advertfloz.application.services.publish_orchestrator import PublishContext, run_tick
from advertfloz.domain.enums import JobStatus, Platform
from advertfloz.infrastructure.meta.graph_client import GraphResponse
from advertfloz.infrastructure.meta.mock_provider import MockGraphClient
from tests.builders import seed_campaign


class IgWorkflowClient(MockGraphClient):
    def __init__(self) -> None:
        super().__init__()
        self.polls = 0

    def _response(self, method: str, path: str, payload: dict) -> GraphResponse:
        self.calls.append((method, path, payload))
        if method == "POST" and path.endswith("/media"):
            return GraphResponse(200, {"id": "container_1"})
        if path == "container_1":
            self.polls += 1
            state = "FINISHED" if self.polls >= 2 else "IN_PROGRESS"
            return GraphResponse(200, {"status_code": state})
        if method == "POST" and path.endswith("/media_publish"):
            return GraphResponse(200, {"id": "media_1", "permalink": "https://example.invalid/m1"})
        return GraphResponse(400, {"error": {"code": 100, "message": "unexpected"}}, "rid", 100, None, "unexpected")


def ctx(client, now):
    return PublishContext(
        graph=client, token_for=lambda p: "token",
        media_url_for=lambda i: f"https://media.example/{i}.jpg",
        target_for=lambda p: "ig-1", now=now, owner="test",
    )


def test_instagram_state_machine_across_ticks(repo):
    seed_campaign(repo, platforms=(Platform.INSTAGRAM,), post_ids=["P001"])
    client = IgWorkflowClient()
    now = datetime.now(UTC)

    first = run_tick(repo, ctx(client, now))
    assert first.claimed == 1
    job = repo.list_jobs()[0]
    assert job.status is JobStatus.PROCESSING_MEDIA
    assert job.last_stage == "CHECK_STATUS"
    assert job.container_id == "container_1"

    # Not due yet (stage delay) — a tick right away claims nothing.
    assert run_tick(repo, ctx(client, now)).claimed == 0

    run_tick(repo, ctx(client, now + timedelta(seconds=45)))
    job = repo.get_job(job.job_id)
    assert job.last_stage in {"CHECK_STATUS", "PUBLISH"}

    run_tick(repo, ctx(client, now + timedelta(seconds=90)))
    run_tick(repo, ctx(client, now + timedelta(seconds=135)))
    job = repo.get_job(job.job_id)
    assert job.status is JobStatus.PUBLISHED, (job.status, job.last_stage)
    assert job.remote_post_id == "media_1"
