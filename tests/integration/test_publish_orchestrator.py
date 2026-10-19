"""Integration tests: publishing orchestration, platform independence and ambiguity."""
from __future__ import annotations

from datetime import UTC, datetime

from advertfloz.application.services.publish_orchestrator import PublishContext, run_tick
from advertfloz.domain.enums import JobStatus, Platform
from advertfloz.infrastructure.meta.graph_client import GraphResponse
from advertfloz.infrastructure.meta.mock_provider import MockGraphClient, Outcome
from tests.builders import seed_campaign


def context(client: MockGraphClient, now: datetime | None = None) -> PublishContext:
    return PublishContext(
        graph=client,
        token_for=lambda platform: "token",
        media_url_for=lambda image_id: f"https://media.example/{image_id}.jpg",
        target_for=lambda platform: "page-1" if platform is Platform.FACEBOOK else "ig-1",
        now=now or datetime.now(UTC),
        owner="test",
    )


class PlatformAwareClient(MockGraphClient):
    """Succeeds for the Page, auth-fails for the Instagram account — deterministically."""

    def _response(self, method: str, path: str, payload: dict) -> GraphResponse:
        if path.startswith("ig-1/"):
            self.calls.append((method, path, payload))
            return GraphResponse(401, {"error": {"code": 190, "message": "Session has expired"}}, "rid", 190, None, "expired")
        return super()._response(method, path, payload)


def test_facebook_success_publishes(repo):
    seed_campaign(repo, platforms=(Platform.FACEBOOK,))
    client = MockGraphClient(default=Outcome.SUCCESS)
    result = run_tick(repo, context(client))
    assert result.published == 2
    jobs = repo.list_jobs(statuses=[JobStatus.PUBLISHED])
    assert len(jobs) == 2
    assert all(j.remote_post_id for j in jobs)


def test_facebook_independent_from_instagram(repo):
    """Facebook succeeds while Instagram fails auth; states must not interfere."""
    seed_campaign(repo, platforms=(Platform.FACEBOOK, Platform.INSTAGRAM))
    client = PlatformAwareClient()
    result = run_tick(repo, context(client), limit=10)
    assert result.published >= 1
    fb = repo.list_jobs(platform=Platform.FACEBOOK, statuses=[JobStatus.PUBLISHED])
    ig = repo.list_jobs(platform=Platform.INSTAGRAM)
    assert fb, "Facebook should publish"
    assert all(j.status is not JobStatus.PUBLISHED for j in ig), "Instagram must not be marked published"
    assert repo.get_flag("pause_instagram") == "1"
    assert not repo.is_paused(Platform.FACEBOOK)


def test_ambiguous_outcome_blocks_retry(repo):
    seed_campaign(repo, platforms=(Platform.FACEBOOK,))
    client = MockGraphClient(default=Outcome.TIMEOUT_AFTER_ACCEPT)
    result = run_tick(repo, context(client))
    assert result.unknown == 2
    jobs = repo.list_jobs()
    assert all(j.status is JobStatus.UNKNOWN_OUTCOME for j in jobs)
    # A second tick must not blindly retry them.
    second = run_tick(repo, context(client))
    assert second.claimed == 0


def test_permanent_payload_failure(repo):
    seed_campaign(repo, platforms=(Platform.FACEBOOK,))
    client = MockGraphClient(default=Outcome.VALIDATION_ERROR)
    result = run_tick(repo, context(client))
    assert result.failed_permanent == 2
    assert all(j.status is JobStatus.FAILED_PERMANENT for j in repo.list_jobs())


def test_transient_failure_backs_off(repo):
    seed_campaign(repo, platforms=(Platform.FACEBOOK,))
    client = MockGraphClient(default=Outcome.SERVER_ERROR)
    result = run_tick(repo, context(client))
    assert result.deferred == 2
    jobs = repo.list_jobs()
    assert all(j.status is JobStatus.FAILED_RETRYABLE for j in jobs)
    assert all(j.next_retry_at for j in jobs)


def test_rate_limit_is_retryable(repo):
    seed_campaign(repo, platforms=(Platform.FACEBOOK,))
    client = MockGraphClient(default=Outcome.RATE_LIMIT)
    result = run_tick(repo, context(client))
    assert result.deferred == 2


def test_transport_timeout_before_send_is_retryable(repo):
    seed_campaign(repo, platforms=(Platform.FACEBOOK,))
    client = MockGraphClient(default=Outcome.TIMEOUT_BEFORE_SEND)
    result = run_tick(repo, context(client))
    assert result.deferred == 2


def test_restriction_pauses_platform(repo):
    seed_campaign(repo, platforms=(Platform.FACEBOOK,))
    client = MockGraphClient(default=Outcome.RESTRICTION)
    run_tick(repo, context(client))
    assert repo.get_flag("pause_facebook") == "1"


def test_missed_beyond_grace_is_never_published_late(repo):
    seed_campaign(repo, platforms=(Platform.FACEBOOK,), schedule="2027-01-01T09:00:00")
    # now is far beyond 2027-01-01 + grace
    now = datetime(2028, 1, 1, tzinfo=UTC)
    client = MockGraphClient(default=Outcome.SUCCESS)
    result = run_tick(repo, context(client, now))
    assert result.missed == 2
    assert all(j.status is JobStatus.MISSED for j in repo.list_jobs())


def test_missing_approval_blocks_dispatch(repo):
    seed_campaign(repo, platforms=(Platform.FACEBOOK,), approved=False)
    client = MockGraphClient(default=Outcome.SUCCESS)
    result = run_tick(repo, context(client))
    assert result.published == 0
    assert all(j.status is JobStatus.VALIDATION_BLOCKED for j in repo.list_jobs())


def test_paused_platform_skips_dispatch(repo):
    seed_campaign(repo, platforms=(Platform.FACEBOOK,))
    repo.pause("facebook")
    client = MockGraphClient(default=Outcome.SUCCESS)
    result = run_tick(repo, context(client))
    assert result.paused_skipped == 2
    assert all(j.status is JobStatus.QUEUED for j in repo.list_jobs())


def test_duplicate_claim_is_prevented(repo):
    seed_campaign(repo, platforms=(Platform.FACEBOOK,), post_ids=["P001"])
    client = MockGraphClient(default=Outcome.SUCCESS)
    first = run_tick(repo, context(client))
    second = run_tick(repo, context(client))
    assert first.claimed == 1
    assert second.claimed == 0
