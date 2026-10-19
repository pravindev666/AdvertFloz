"""Deterministic mock Meta provider for tests and demo mode.

Every scripted outcome maps to a real-world failure the retry policy must handle (PRD §9).
Mocks are used only in tests/demo mode; configured mode always uses HttpGraphClient.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .graph_client import GraphResponse


class Outcome(str, Enum):
    SUCCESS = "success"
    REVOKED_TOKEN = "revoked_token"
    MISSING_SCOPE = "missing_scope"
    VALIDATION_ERROR = "validation_error"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    TIMEOUT_BEFORE_SEND = "timeout_before_send"
    TIMEOUT_AFTER_ACCEPT = "timeout_after_accept"
    MALFORMED = "malformed"
    RESTRICTION = "restriction"


class TransportTimeout(RuntimeError):
    """Raised when the request never reached the provider (safe to retry)."""


@dataclass
class MockGraphClient:
    script: list[Outcome] = field(default_factory=list)
    default: Outcome = Outcome.SUCCESS
    calls: list[tuple[str, str, dict]] = field(default_factory=list)
    id_counter: int = 1000

    def _next(self) -> Outcome:
        if self.script:
            return self.script.pop(0)
        return self.default

    def _response(self, method: str, path: str, payload: dict[str, Any]) -> GraphResponse:
        outcome = self._next()
        self.calls.append((method, path, payload))
        self.id_counter += 1
        rid = f"mock-{self.id_counter}"

        if outcome is Outcome.TIMEOUT_BEFORE_SEND:
            raise TransportTimeout("connection timed out before the request was sent")
        if outcome is Outcome.TIMEOUT_AFTER_ACCEPT:
            return GraphResponse(status_code=200, json={}, request_id=rid, ambiguous=True,
                                 error_message="no response body after possible acceptance")
        if outcome is Outcome.REVOKED_TOKEN:
            return GraphResponse(401, {"error": {"code": 190, "message": "Session has expired"}}, rid, 190, None, "Session has expired")
        if outcome is Outcome.MISSING_SCOPE:
            return GraphResponse(403, {"error": {"code": 200, "message": "Permissions error"}}, rid, 200, None, "Permissions error")
        if outcome is Outcome.VALIDATION_ERROR:
            return GraphResponse(400, {"error": {"code": 100, "message": "Invalid parameter"}}, rid, 100, None, "Invalid parameter")
        if outcome is Outcome.RATE_LIMIT:
            return GraphResponse(429, {"error": {"code": 4, "message": "Application request limit reached"}}, rid, 4, None, "Application request limit reached")
        if outcome is Outcome.SERVER_ERROR:
            return GraphResponse(500, {"error": {"code": 1, "message": "Internal server error"}}, rid, 1, None, "Internal server error")
        if outcome is Outcome.RESTRICTION:
            return GraphResponse(400, {"error": {"code": 368, "message": "The action attempted has been deemed abusive or is otherwise disallowed"}}, rid, 368, None, "account restricted")
        if outcome is Outcome.MALFORMED:
            # An unparseable body means success cannot be confirmed: treat it as ambiguous.
            return GraphResponse(200, {}, rid, None, None, "", raw_text="<html>not json</html>", ambiguous=True)
        # SUCCESS
        return GraphResponse(200, {"id": f"mock_id_{self.id_counter}", "permalink": f"https://example.invalid/{self.id_counter}"}, rid)

    def get(self, path: str, params: dict[str, Any], token: str) -> GraphResponse:
        return self._response("GET", path, params)

    def post(self, path: str, data: dict[str, Any], token: str) -> GraphResponse:
        return self._response("POST", path, data)


@dataclass
class MockInstagramWorkflow:
    """Scripts the create-container → process → publish state machine across ticks."""

    process_polls_before_ready: int = 1
    polls: int = 0
    container_id: str = "container_1"
    published_id: str = "media_1"

    def container_create(self) -> GraphResponse:
        return GraphResponse(200, {"id": self.container_id})

    def container_status(self) -> GraphResponse:
        self.polls += 1
        state = "FINISHED" if self.polls > self.process_polls_before_ready else "IN_PROGRESS"
        return GraphResponse(200, {"id": self.container_id, "status_code": state})

    def publish(self) -> GraphResponse:
        return GraphResponse(200, {"id": self.published_id, "permalink": f"https://example.invalid/{self.published_id}"})
