"""Canonical validation rules and constants for the v1.7 CSV / ZIP contract.

Single source of truth shared by the importer, the vendored validator, the UI and tests.
Changing anything here changes the contract and requires updating fixtures, docs and the
vendored tools together (PRD §0 source-of-truth rule).
"""
from __future__ import annotations

import re
from zoneinfo import ZoneInfo

from .enums import DisclosureStatus, Platform, Severity
from .models import ValidationIssue
from .scheduling import DstResult, classify_dst, is_valid_iana, parse_local

PLAN_HEADER = [
    "post_id",
    "scheduled_at",
    "timezone",
    "platforms",
    "image_id",
    "caption",
    "enabled",
    "campaign_tag",
    "facebook_caption",
    "instagram_caption",
    "alt_text",
    "destination_url",
    "grace_minutes",
    "ai_disclosure_status",
    "notes",
]

PROMPT_HEADER = [
    "post_id",
    "image_id",
    "headline",
    "core_visual_concept",
    "visual_grammar",
    "prompt",
    "negative_prompt",
    "aspect_ratio",
    "language",
    "alt_text",
    "product_claims_used",
]

PLATFORM_VALUES = {"facebook", "instagram", "facebook;instagram"}
DISCLOSURE_VALUES = {d.value for d in DisclosureStatus}

POST_ID_RE = re.compile(r"P(\d{3})")
IMAGE_FILENAME_RE = re.compile(r"[1-9]\d{0,2}\.jpg")
ZIP_NAME_RE = re.compile(r"advertfloz_images_(\d{3})_(\d{3})\.zip")

MAX_INSTAGRAM_CAPTION = 2200
MAX_INSTAGRAM_HASHTAGS = 5          # conservative application policy, re-verified live
MAX_GRACE_MINUTES = 1440
MAX_ROWS = 365

#: 13 fixed external-AI batch ranges (PRD §5).
BATCH_RANGES: list[tuple[int, int]] = [(n, min(n + 29, 365)) for n in range(1, 361, 30)] + [(361, 365)]


def range_code(start: int, end: int) -> str:
    return f"{start:03d}_{end:03d}"


def batch_range_codes() -> list[str]:
    return [range_code(a, b) for a, b in BATCH_RANGES]


def canonical_zip_name(start: int, end: int) -> str:
    return f"advertfloz_images_{start:03d}_{end:03d}.zip"


def parse_zip_range(name: str) -> tuple[int, int] | None:
    match = ZIP_NAME_RE.fullmatch(name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def post_ordinal(post_id: str) -> int | None:
    match = POST_ID_RE.fullmatch(post_id.strip())
    if not match:
        return None
    return int(match.group(1))


def expected_image_filename(image_id: int) -> str:
    return f"{image_id}.jpg"


def truncate(value: str, limit: int = 60) -> str:
    """Safely truncate hostile content for error messages."""
    if value is None:
        return ""
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _issue(line: int, field: str, value: str, rule: str, message: str, severity: Severity = Severity.DANGER) -> ValidationIssue:
    return ValidationIssue(row=line, field=field, value=truncate(value), rule=rule, message=message, severity=severity)


def validate_plan_header(fieldnames: list[str] | None) -> list[ValidationIssue]:
    if fieldnames != PLAN_HEADER:
        return [
            ValidationIssue(
                row=None,
                field="header",
                value=truncate(str(fieldnames)),
                rule="plan.header",
                message=f"Header mismatch. Expected {PLAN_HEADER}; found {fieldnames}",
            )
        ]
    return []


def count_hashtags(caption: str) -> int:
    return len(re.findall(r"(?<![\w])#[\w]+", caption, flags=re.UNICODE))


def effective_caption(row: dict, platform: Platform) -> str:
    if platform is Platform.FACEBOOK:
        return (row.get("facebook_caption") or "").strip() or (row.get("caption") or "")
    return (row.get("instagram_caption") or "").strip() or (row.get("caption") or "")


def parse_platforms(value: str) -> tuple[Platform, ...] | None:
    if value not in PLATFORM_VALUES:
        return None
    if value == "facebook":
        return (Platform.FACEBOOK,)
    if value == "instagram":
        return (Platform.INSTAGRAM,)
    return (Platform.FACEBOOK, Platform.INSTAGRAM)


def validate_plan_row(row: dict, line: int, *, require_image_ordinal_match: bool = True) -> list[ValidationIssue]:
    """Validate one campaign_plan.csv data row. Returns blocking errors and warnings."""
    issues: list[ValidationIssue] = []

    post_id = (row.get("post_id") or "").strip()
    ordinal = post_ordinal(post_id)
    if ordinal is None or not 1 <= ordinal <= 365:
        issues.append(_issue(line, "post_id", post_id, "plan.post_id", "post_id must be P001–P365"))

    image_id: int | None = None
    raw_image_id = (row.get("image_id") or "").strip()
    try:
        image_id = int(raw_image_id)
        if not 1 <= image_id <= 365:
            raise ValueError
    except (ValueError, TypeError):
        image_id = None
        issues.append(_issue(line, "image_id", raw_image_id, "plan.image_id", "image_id must be an integer 1–365"))
    if image_id is not None and ordinal is not None and require_image_ordinal_match and image_id != ordinal:
        issues.append(
            _issue(line, "image_id", raw_image_id, "plan.image_map",
                   f"image_id must match post ordinal under the v1.7 default map; expected {ordinal}")
        )

    if row.get("enabled") != "false":
        issues.append(
            _issue(line, "enabled", str(row.get("enabled")), "plan.enabled",
                   "enabled must be the exact lowercase string false in external-AI output")
        )

    if row.get("platforms") not in PLATFORM_VALUES:
        issues.append(
            _issue(line, "platforms", str(row.get("platforms")), "plan.platforms",
                   "platforms must be facebook, instagram or facebook;instagram")
        )

    raw_dt = row.get("scheduled_at") or ""
    dt = parse_local(raw_dt)
    if dt is None:
        issues.append(
            _issue(line, "scheduled_at", raw_dt, "plan.scheduled_at",
                   "scheduled_at must be strict YYYY-MM-DDTHH:MM:SS local wall time")
        )

    tz_name = (row.get("timezone") or "").strip()
    if not is_valid_iana(tz_name):
        issues.append(
            _issue(line, "timezone", tz_name, "plan.timezone",
                   f"unknown IANA timezone {tz_name!r}; use e.g. Asia/Kolkata, never IST")
        )
    elif dt is not None:
        dst = classify_dst(dt, ZoneInfo(tz_name))
        if dst is DstResult.NONEXISTENT:
            issues.append(
                _issue(line, "scheduled_at", raw_dt, "plan.dst_nonexistent",
                       "local time does not exist because of a DST spring-forward gap")
            )
        elif dst is DstResult.AMBIGUOUS:
            issues.append(
                _issue(line, "scheduled_at", raw_dt, "plan.dst_ambiguous",
                       "ambiguous local time during DST fall-back; choose an explicit alternative time")
            )

    if (row.get("ai_disclosure_status") or "") not in DISCLOSURE_VALUES:
        issues.append(
            _issue(line, "ai_disclosure_status", str(row.get("ai_disclosure_status")), "plan.disclosure",
                   f"ai_disclosure_status must be one of {sorted(DISCLOSURE_VALUES)}")
        )

    destination = row.get("destination_url") or ""
    if destination and not destination.startswith("https://"):
        issues.append(
            _issue(line, "destination_url", destination, "plan.destination_url",
                   "destination_url must be blank or a verified HTTPS URL")
        )

    platforms = parse_platforms(row.get("platforms") or "")
    if platforms and Platform.INSTAGRAM in platforms:
        caption = effective_caption(row, Platform.INSTAGRAM)
        if len(caption) > MAX_INSTAGRAM_CAPTION:
            issues.append(
                _issue(line, "instagram_caption", caption, "plan.instagram_caption_limit",
                       f"Instagram caption exceeds {MAX_INSTAGRAM_CAPTION} characters")
            )
        tags = count_hashtags(caption)
        if tags > MAX_INSTAGRAM_HASHTAGS:
            issues.append(
                _issue(line, "instagram_caption", caption, "plan.hashtags",
                       f"{tags} hashtags found; the conservative v1.7 policy allows at most "
                       f"{MAX_INSTAGRAM_HASHTAGS}", severity=Severity.WARNING)
            )

    grace = (row.get("grace_minutes") or "").strip()
    if grace:
        try:
            value = int(grace)
            if not 0 <= value <= MAX_GRACE_MINUTES:
                raise ValueError
        except (ValueError, TypeError):
            issues.append(
                _issue(line, "grace_minutes", grace, "plan.grace_minutes",
                       f"grace_minutes must be blank or an integer 0–{MAX_GRACE_MINUTES}")
            )

    return issues
