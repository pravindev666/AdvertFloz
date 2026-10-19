"""Meta Graph API client: real HTTP client, deterministic mock, and error classification.

The client is deliberately thin. Adapters (facebook_pages, instagram_publish) express the
provider workflows; this module only performs calls and maps failures to ``ErrorClass`` so
the retry policy can reason about them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ...domain.enums import ErrorClass
from ..security.redaction import redact

DEFAULT_TIMEOUT = 20


@dataclass
class GraphResponse:
    status_code: int
    json: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""
    error_code: int | None = None
    error_subcode: int | None = None
    error_message: str = ""
    raw_text: str = ""
    ambiguous: bool = False   # request may have been accepted but response was lost

    @property
    def ok(self) -> bool:
        # An ambiguous response (request may have been accepted but no body arrived) is never
        # treated as success — it becomes UNKNOWN_OUTCOME and is reconciled before any retry.
        return 200 <= self.status_code < 300 and not self.json.get("error") and not self.ambiguous

    def sanitized_summary(self) -> str:
        if self.error_message:
            return redact(f"status={self.status_code} code={self.error_code} subcode={self.error_subcode} msg={self.error_message[:200]}")
        return redact(f"status={self.status_code} id={self.json.get('id', '')}")


class GraphClient(Protocol):
    def get(self, path: str, params: dict[str, Any], token: str) -> GraphResponse: ...
    def post(self, path: str, data: dict[str, Any], token: str) -> GraphResponse: ...


# --------------------------------------------------------------------- classification
def classify_graph_error(response: GraphResponse) -> ErrorClass:
    """Map a provider response to a retry class (PRD §7.4)."""
    if response.ambiguous:
        return ErrorClass.AMBIGUOUS
    code = response.error_code
    status = response.status_code
    message = (response.error_message or "").lower()

    # Token / permission failures → pause the channel and require reauthorization.
    if code in {190, 102, 463, 467} or "access token" in message or "session has expired" in message:
        return ErrorClass.AUTH
    if code in {10, 200, 202} or ("permission" in message and "publish" in message):
        return ErrorClass.AUTH
    # Account / integrity restrictions → circuit breaker.
    if code in {368, 131000, 131031} or "restricted" in message or "disabled" in message:
        return ErrorClass.RESTRICTION
    # Confirmed rate limiting → backoff honoring provider hints.
    if code in {4, 17, 32, 613} or status == 429:
        return ErrorClass.RATE_LIMIT
    # Validation/payload problems are permanent.
    if code in {100, 324, 352} or status in {400, 415, 422}:
        return ErrorClass.PAYLOAD
    if status >= 500:
        return ErrorClass.TRANSIENT
    if status in {408, 504}:
        return ErrorClass.TRANSIENT
    return ErrorClass.UNKNOWN


# --------------------------------------------------------------------- real client
class HttpGraphClient:
    """Real Graph API client. Requires network + a valid token (Phase 0)."""

    def __init__(self, base_url: str = "https://graph.facebook.com", version: str = "v21.0"):
        self.base_url = base_url.rstrip("/")
        self.version = version

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{self.version}/{path.lstrip('/')}"

    def _parse(self, response: Any) -> GraphResponse:
        request_id = ""
        try:
            request_id = response.headers.get("x-fb-trace-id", "")
        except Exception:
            pass
        try:
            payload = response.json()
        except Exception:
            return GraphResponse(status_code=response.status_code, raw_text=response.text[:500], request_id=request_id)
        error = payload.get("error") if isinstance(payload, dict) else None
        if error:
            return GraphResponse(
                status_code=response.status_code, json=payload, request_id=request_id,
                error_code=error.get("code"), error_subcode=error.get("error_subcode"),
                error_message=error.get("message", ""),
            )
        return GraphResponse(status_code=response.status_code, json=payload, request_id=request_id)

    def get(self, path: str, params: dict[str, Any], token: str) -> GraphResponse:
        import requests

        query = dict(params)
        query["access_token"] = token
        resp = requests.get(self._url(path), params=query, timeout=DEFAULT_TIMEOUT)
        return self._parse(resp)

    def post(self, path: str, data: dict[str, Any], token: str) -> GraphResponse:
        import requests

        body = dict(data)
        body["access_token"] = token
        resp = requests.post(self._url(path), data=body, timeout=DEFAULT_TIMEOUT)
        return self._parse(resp)
