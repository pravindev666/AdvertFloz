"""Unit tests for scheduling/DST/activation-buffer rules."""
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from advertfloz.domain.scheduling import (
    DstResult,
    assess_buffer,
    classify_dst,
    is_missed,
    is_valid_iana,
    longest_consecutive_ready_days,
    parse_local,
    to_utc,
)


def test_parse_local_strict():
    assert parse_local("2027-01-01T09:00:00") is not None
    assert parse_local("2027-01-01 09:00:00") is None
    assert parse_local("2027-01-01T09:00") is None


def test_iana_validation():
    assert is_valid_iana("Asia/Kolkata")
    assert not is_valid_iana("IST")
    assert not is_valid_iana("Not/AZone")


def test_dst_classification():
    tz = ZoneInfo("America/New_York")
    assert classify_dst(datetime(2027, 3, 14, 2, 30), tz) is DstResult.NONEXISTENT
    assert classify_dst(datetime(2027, 11, 7, 1, 30), tz) is DstResult.AMBIGUOUS
    assert classify_dst(datetime(2027, 5, 1, 9, 0), tz) is DstResult.OK


def test_to_utc():
    dt = to_utc("2027-01-01T09:00:00", "Asia/Kolkata")
    assert dt is not None and dt.tzinfo is not None


def test_grace_and_missed():
    now = datetime(2027, 1, 1, 4, 0, tzinfo=UTC)  # 09:30 IST
    assert not is_missed("2027-01-01T09:00:00", "Asia/Kolkata", now, 60)
    late = datetime(2027, 1, 1, 6, 0, tzinfo=UTC)  # 11:30 IST
    assert is_missed("2027-01-01T09:00:00", "Asia/Kolkata", late, 60)


def test_buffer_gate():
    assert assess_buffer(5).blocks_activation
    assert assess_buffer(18).warns and not assess_buffer(18).blocks_activation
    assert not assess_buffer(30).warns


def test_longest_consecutive():
    assert longest_consecutive_ready_days({1, 2, 3, 5, 6}, [1, 2, 3, 4, 5, 6]) == 3
    assert longest_consecutive_ready_days(set(), [1, 2]) == 0
