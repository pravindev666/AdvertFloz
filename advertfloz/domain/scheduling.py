"""Scheduling rules: strict local time parsing, DST correctness, grace and activation windows.

The DST logic here mirrors the supplied ``validate_campaign_package_v1.7.py`` so the app,
the vendored validator and the tests agree on what a valid local time is.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LOCAL_FORMAT = "%Y-%m-%dT%H:%M:%S"


class DstResult(str, Enum):
    OK = "ok"
    NONEXISTENT = "nonexistent"   # spring-forward gap
    AMBIGUOUS = "ambiguous"       # fall-back overlap


def is_valid_iana(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return False


def parse_local(raw: str) -> datetime | None:
    """Parse a strict ``YYYY-MM-DDTHH:MM:SS`` wall time, or None if malformed."""
    try:
        dt = datetime.strptime(raw, LOCAL_FORMAT)
    except (ValueError, TypeError):
        return None
    if dt.strftime(LOCAL_FORMAT) != raw:
        return None
    return dt


def classify_dst(dt: datetime, tz: ZoneInfo) -> DstResult:
    """Detect nonexistent (spring-forward) and ambiguous (fall-back) local times."""
    a0 = dt.replace(tzinfo=tz, fold=0)
    a1 = dt.replace(tzinfo=tz, fold=1)
    back0 = a0.astimezone(UTC).astimezone(tz).replace(tzinfo=None)
    back1 = a1.astimezone(UTC).astimezone(tz).replace(tzinfo=None)
    valid0 = back0 == dt
    valid1 = back1 == dt
    if not valid0 and not valid1:
        return DstResult.NONEXISTENT
    if valid0 and valid1 and a0.utcoffset() != a1.utcoffset():
        return DstResult.AMBIGUOUS
    return DstResult.OK


def to_utc(raw: str, tz_name: str) -> datetime | None:
    """Convert a validated local wall time to an aware UTC datetime."""
    dt = parse_local(raw)
    if dt is None or not is_valid_iana(tz_name):
        return None
    return dt.replace(tzinfo=ZoneInfo(tz_name)).astimezone(UTC)


def local_display(raw: str, tz_name: str) -> str:
    dt = parse_local(raw)
    if dt is None:
        return raw
    return f"{raw} ({tz_name})"


# ------------------------------------------------------------------ grace window
DEFAULT_MAX_GRACE_MINUTES = 1440


def grace_window_minutes(grace_minutes: int | None) -> int:
    if grace_minutes is None:
        return 0
    return max(0, min(int(grace_minutes), DEFAULT_MAX_GRACE_MINUTES))


def is_within_grace(scheduled_at: str, tz_name: str, now: datetime, grace_minutes: int | None) -> bool:
    due = to_utc(scheduled_at, tz_name)
    if due is None:
        return False
    return now <= due + timedelta(minutes=grace_window_minutes(grace_minutes))


def is_missed(scheduled_at: str, tz_name: str, now: datetime, grace_minutes: int | None) -> bool:
    due = to_utc(scheduled_at, tz_name)
    if due is None:
        return False
    return now > due + timedelta(minutes=grace_window_minutes(grace_minutes))


# ------------------------------------------------------------------ activation gate
MIN_READY_DAYS = 14
WARN_READY_DAYS = 21
DEFAULT_ACTIVATION_WINDOW_DAYS = 30


@dataclass(frozen=True)
class BufferAssessment:
    consecutive_ready_days: int
    blocks_activation: bool
    warns: bool
    message: str


def assess_buffer(consecutive_ready_days: int) -> BufferAssessment:
    """Asset buffer rule: warn below 21 days, block normal activation below 14."""
    if consecutive_ready_days < MIN_READY_DAYS:
        return BufferAssessment(
            consecutive_ready_days,
            blocks_activation=True,
            warns=True,
            message=(
                f"Only {consecutive_ready_days} consecutive approved+synced day(s); "
                f"at least {MIN_READY_DAYS} are required before normal activation."
            ),
        )
    if consecutive_ready_days < WARN_READY_DAYS:
        return BufferAssessment(
            consecutive_ready_days,
            blocks_activation=False,
            warns=True,
            message=(
                f"{consecutive_ready_days} consecutive day(s) ready; "
                f"below the {WARN_READY_DAYS}-day comfort buffer."
            ),
        )
    return BufferAssessment(consecutive_ready_days, False, False, f"{consecutive_ready_days} days ready.")


def longest_consecutive_ready_days(ready_image_ids: set[int], ordered_image_ids: list[int]) -> int:
    """Longest run of consecutive ordered IDs that are all ready."""
    best = current = 0
    for iid in ordered_image_ids:
        if iid in ready_image_ids:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def activation_window_end(start_date: str, days: int = DEFAULT_ACTIVATION_WINDOW_DAYS) -> str:
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return ""
    end = start + timedelta(days=days - 1)
    return end.strftime("%Y-%m-%d")
