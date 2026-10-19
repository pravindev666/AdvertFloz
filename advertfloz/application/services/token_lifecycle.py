"""Token lifecycle: expiry tracking, T-14 alerts and renewal decisions (FR-022).

Refresh happens only through the chosen flow's supported mechanism. When renewal is
unsupported or fails, the channel is paused and reauthorization is required.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ...domain.enums import AuthFlow, ConnectionState, Platform
from ...domain.models import Connection

ALERT_DAYS_BEFORE_EXPIRY = 14


@dataclass
class TokenHealth:
    platform: Platform
    expires_at: str
    days_remaining: int | None
    expired: bool
    needs_alert: bool
    renewal: str            # refresh | reauth | none
    message: str


def _parse(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def assess_token_health(connection: Connection, now: datetime | None = None) -> TokenHealth:
    now = now or datetime.now(UTC)
    expiry = _parse(connection.expires_at)
    if expiry is None:
        return TokenHealth(
            connection.provider, "", None, False, False, "none",
            "Expiry unknown for this flow; revalidate periodically and reconnect if publishing fails.",
        )
    days = (expiry - now).days
    expired = expiry <= now
    flow = connection.auth_flow
    renewal = "refresh" if flow is AuthFlow.FACEBOOK_LOGIN else "reauth"
    if expired:
        return TokenHealth(connection.provider, connection.expires_at, days, True, True, "reauth",
                           "Token expired; reauthorize this platform.")
    return TokenHealth(
        connection.provider, connection.expires_at, days, False, days <= ALERT_DAYS_BEFORE_EXPIRY, renewal,
        f"Token expires in {days} day(s).",
    )


def should_pause(health: TokenHealth, refresh_failed: bool) -> bool:
    """Pause the channel when the token is expired or renewal is unsupported/failed."""
    return health.expired or refresh_failed or health.renewal == "reauth" and health.needs_alert


def next_validation_time(now: datetime | None = None, hours: int = 24) -> str:
    now = now or datetime.now(UTC)
    return (now + timedelta(hours=hours)).isoformat(timespec="seconds")


def connection_is_usable(state: ConnectionState) -> bool:
    return state in {ConnectionState.TARGET_SELECTED, ConnectionState.TEST_PASSED}
