"""Unit tests for CSV validation rules (FR-005, fault register)."""
from __future__ import annotations

from advertfloz.domain.validation_rules import (
    PLAN_HEADER,
    validate_plan_header,
    validate_plan_row,
)


def base_row(**overrides) -> dict:
    row = {
        "post_id": "P001",
        "scheduled_at": "2027-01-01T09:00:00",
        "timezone": "Asia/Kolkata",
        "platforms": "facebook",
        "image_id": "1",
        "caption": "Hello",
        "enabled": "false",
        "campaign_tag": "tag",
        "facebook_caption": "",
        "instagram_caption": "",
        "alt_text": "",
        "destination_url": "",
        "grace_minutes": "",
        "ai_disclosure_status": "not_reviewed",
        "notes": "",
    }
    row.update(overrides)
    return row


def errors(row, line=2):
    return [i for i in validate_plan_row(row, line) if i.is_blocking]


def warnings(row, line=2):
    return [i for i in validate_plan_row(row, line) if not i.is_blocking]


def test_header_exact():
    assert validate_plan_header(PLAN_HEADER) == []
    assert validate_plan_header(PLAN_HEADER + ["extra"])


def test_valid_row_passes():
    assert errors(base_row()) == []


def test_invalid_timezone_abbreviation():
    issues = errors(base_row(timezone="IST"))
    assert any("timezone" in i.field for i in issues)


def test_bad_boolean_rejected():
    issues = errors(base_row(enabled="yes"))
    assert any(i.field == "enabled" for i in issues)


def test_enabled_true_rejected_for_ai_output():
    assert errors(base_row(enabled="true"))


def test_duplicate_post_and_image_detected_by_caller():
    # row-level validation only checks shape; duplicate detection is at plan level
    assert errors(base_row(post_id="P1", image_id="1"))


def test_dst_nonexistent_time():
    issues = errors(base_row(scheduled_at="2027-03-14T02:30:00", timezone="America/New_York"))
    assert any("dst" in i.rule for i in issues)


def test_dst_ambiguous_time():
    issues = errors(base_row(scheduled_at="2027-11-07T01:30:00", timezone="America/New_York"))
    assert any("dst" in i.rule for i in issues)


def test_destination_url_must_be_https():
    assert errors(base_row(destination_url="http://example.com"))
    assert errors(base_row(destination_url="https://example.com")) == []


def test_caption_over_limit_rejected():
    row = base_row(platforms="instagram", caption="x" * 2300, image_id="1")
    assert any(i.rule == "plan.instagram_caption_limit" for i in errors(row))


def test_hashtag_policy_is_warning_not_blocking():
    row = base_row(platforms="instagram", caption="#a #b #c #d #e #f")
    assert errors(row) == []
    assert any("hashtag" in i.rule for i in warnings(row))


def test_unicode_and_multiline_preserved():
    caption = "தமிழ் + emoji 🌟 caption\nSecond line."
    issues = errors(base_row(caption=caption, platforms="instagram"))
    assert issues == []


def test_grace_minutes_bounds():
    assert errors(base_row(grace_minutes="1441"))
    assert errors(base_row(grace_minutes="abc"))
    assert errors(base_row(grace_minutes="30")) == []
