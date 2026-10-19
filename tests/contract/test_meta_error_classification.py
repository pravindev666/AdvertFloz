"""Contract tests: Meta adapter error classification for every mocked outcome (FR-020)."""
from __future__ import annotations

import pytest

from advertfloz.domain.enums import ErrorClass
from advertfloz.infrastructure.meta.graph_client import GraphResponse, classify_graph_error
from advertfloz.infrastructure.meta.mock_provider import MockGraphClient, Outcome

EXPECTED = {
    Outcome.REVOKED_TOKEN: ErrorClass.AUTH,
    Outcome.MISSING_SCOPE: ErrorClass.AUTH,
    Outcome.RESTRICTION: ErrorClass.RESTRICTION,
    Outcome.RATE_LIMIT: ErrorClass.RATE_LIMIT,
    Outcome.VALIDATION_ERROR: ErrorClass.PAYLOAD,
    Outcome.SERVER_ERROR: ErrorClass.TRANSIENT,
    Outcome.TIMEOUT_AFTER_ACCEPT: ErrorClass.AMBIGUOUS,
}


@pytest.mark.parametrize("outcome,expected", list(EXPECTED.items()))
def test_mock_outcomes_classified(outcome, expected):
    client = MockGraphClient(default=outcome)
    response = client.post("123/photos", {}, "token")
    assert classify_graph_error(response) is expected


def test_success_is_ok():
    client = MockGraphClient(default=Outcome.SUCCESS)
    response = client.get("me", {}, "token")
    assert response.ok
    assert response.json["id"]


def test_timeout_before_send_raises_transport():
    from advertfloz.infrastructure.meta.mock_provider import TransportTimeout

    client = MockGraphClient(default=Outcome.TIMEOUT_BEFORE_SEND)
    with pytest.raises(TransportTimeout):
        client.get("me", {}, "token")


def test_ambiguous_is_not_ok():
    client = MockGraphClient(default=Outcome.TIMEOUT_AFTER_ACCEPT)
    response = client.get("me", {}, "token")
    assert not response.ok
    assert response.ambiguous


def test_malformed_response_is_not_ok():
    client = MockGraphClient(default=Outcome.MALFORMED)
    response = client.get("me", {}, "token")
    assert not response.ok


def test_sanitized_summary_never_leaks_token():
    response = GraphResponse(401, {"error": {"code": 190, "message": "Bearer EAAabcdefghijklmnopqrstuvwx"}}, "r", 190, None,
                             "Bearer EAAabcdefghijklmnopqrstuvwx")
    assert "EAA" not in response.sanitized_summary()
