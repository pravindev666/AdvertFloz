"""Campaign import: CSV parsing/validation and revision assembly (FR-005, FR-010).

Strict header, enum, date/DST, boolean, caption and URL checks with blocking errors kept
separate from non-blocking warnings. Nothing here activates a post: every imported row keeps
``enabled`` as supplied (which the external AI contract mandates is ``false``).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from ...domain.enums import DisclosureStatus, Severity
from ...domain.models import Post, ValidationIssue
from ...domain.validation_rules import (
    MAX_ROWS,
    parse_platforms,
    post_ordinal,
    validate_plan_header,
    validate_plan_row,
)
from ...infrastructure.storage.zip_validation import AssetInfo, ZipInspection, inspect_zip, merge_inspections

__all__ = [
    "ImportLimits",
    "ImportResult",
    "read_plan_csv",
    "validate_plan",
    "assemble_import",
]

_SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.DANGER: 1, Severity.WARNING: 2, Severity.INFO: 3}


@dataclass(frozen=True)
class ImportLimits:
    max_image_bytes: int = 8 * 1024 * 1024
    max_expanded_bytes: int = 1_000_000_000
    max_archive_bytes: int = 250 * 1024 * 1024
    max_rows: int = MAX_ROWS


@dataclass
class ImportResult:
    campaign_id: str = ""
    campaign_name: str = ""
    campaign_tag: str = ""
    default_timezone: str = ""
    start_date: str = ""
    end_date: str = ""
    posts: list[Post] = field(default_factory=list)
    assets: dict[int, AssetInfo] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)
    plan_hash: str = ""

    @property
    def blocking(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.is_blocking]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if not i.is_blocking]

    @property
    def ok(self) -> bool:
        return not self.blocking

    def platform_counts(self) -> dict[str, int]:
        counts = {"facebook": 0, "instagram": 0}
        for post in self.posts:
            for platform in post.platforms:
                counts[platform.value] += 1
        return counts

    def missing_image_ids(self) -> list[int]:
        referenced = {p.image_id for p in self.posts}
        return sorted(i for i in referenced if i not in self.assets)

    def mapping_complete(self) -> bool:
        return not self.missing_image_ids()


def read_plan_csv(path: str | Path) -> tuple[list[str], list[dict]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    return fieldnames, rows


def validate_plan(fieldnames: list[str], rows: list[dict], limits: ImportLimits | None = None) -> list[ValidationIssue]:
    limits = limits or ImportLimits()
    issues = list(validate_plan_header(fieldnames))
    if issues:
        return issues  # header must be exact before row validation is meaningful

    if not rows:
        issues.append(ValidationIssue(None, "rows", "", "plan.empty", "No campaign rows found"))
        return issues
    if len(rows) > limits.max_rows:
        issues.append(
            ValidationIssue(None, "rows", str(len(rows)), "plan.max_rows", f"More than {limits.max_rows} rows")
        )

    post_ids: list[str] = []
    image_ids: list[int] = []
    for line, row in enumerate(rows, start=2):
        for issue in validate_plan_row(row, line):
            issues.append(issue)
        post_ids.append((row.get("post_id") or "").strip())
        try:
            image_ids.append(int((row.get("image_id") or "").strip()))
        except (ValueError, TypeError):
            pass

    if len(post_ids) != len(set(post_ids)):
        issues.append(ValidationIssue(None, "post_id", "", "plan.duplicate_post", "Duplicate post_id values"))
    if len(image_ids) != len(set(image_ids)):
        issues.append(ValidationIssue(None, "image_id", "", "plan.duplicate_image", "Duplicate image_id values"))
    return issues


def _build_post(row: dict, campaign_id: str, revision_id: int) -> Post:
    platforms = parse_platforms(row.get("platforms") or "") or ()
    ordinal = post_ordinal((row.get("post_id") or "").strip()) or 0
    grace = (row.get("grace_minutes") or "").strip()
    return Post(
        post_id=(row.get("post_id") or "").strip(),
        campaign_id=campaign_id,
        revision_id=revision_id,
        image_id=int((row.get("image_id") or ordinal) or 0),
        scheduled_at=(row.get("scheduled_at") or "").strip(),
        timezone=(row.get("timezone") or "").strip(),
        platforms=tuple(platforms),
        caption=row.get("caption") or "",
        facebook_caption=row.get("facebook_caption") or "",
        instagram_caption=row.get("instagram_caption") or "",
        alt_text=row.get("alt_text") or "",
        destination_url=row.get("destination_url") or "",
        grace_minutes=int(grace) if grace else None,
        campaign_tag=(row.get("campaign_tag") or "").strip(),
        ai_disclosure_status=DisclosureStatus((row.get("ai_disclosure_status") or "not_reviewed").strip()),
        enabled=(row.get("enabled") == "true"),
        notes=row.get("notes") or "",
    )


def assemble_import(
    *,
    campaign_id: str,
    campaign_name: str,
    revision_id: int,
    plan_path: str | Path,
    zip_paths: list[str | Path] | None = None,
    limits: ImportLimits | None = None,
    manifest_path: str | Path | None = None,
) -> ImportResult:
    """Run the full dry-run import: CSV validation + ZIP inspection + cross-checks."""
    import hashlib

    limits = limits or ImportLimits()
    fieldnames, rows = read_plan_csv(plan_path)
    issues = validate_plan(fieldnames, rows, limits)

    plan_hash = hashlib.sha256(Path(plan_path).read_bytes()).hexdigest()

    posts = [_build_post(row, campaign_id, revision_id) for row in rows]
    tags = [p.campaign_tag for p in posts if p.campaign_tag]
    tz = next((p.timezone for p in posts if p.timezone), "")
    start = min((p.scheduled_at[:10] for p in posts if p.scheduled_at), default="")
    end = max((p.scheduled_at[:10] for p in posts if p.scheduled_at), default="")

    assets: dict[int, AssetInfo] = {}
    if zip_paths:
        inspections: list[ZipInspection] = []
        for zp in zip_paths:
            if Path(zp).stat().st_size > limits.max_archive_bytes:
                issues.append(ValidationIssue(None, "zip", Path(zp).name, "zip.archive_size", "Archive exceeds the configured byte limit"))
                continue
            inspections.append(
                inspect_zip(zp, max_image_bytes=limits.max_image_bytes, max_expanded_bytes=limits.max_expanded_bytes)
            )
        assets, zip_issues = merge_inspections(inspections)
        issues.extend(zip_issues)

    result = ImportResult(
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        campaign_tag=tags[0] if tags else "",
        default_timezone=tz,
        start_date=start,
        end_date=end,
        posts=posts,
        assets=assets,
        issues=issues,
        plan_hash=plan_hash,
    )

    if zip_paths:
        for image_id in result.missing_image_ids():
            issues.append(
                ValidationIssue(None, "image_id", str(image_id), "import.missing_image", f"Missing referenced image {image_id}.jpg")
            )
        extras = sorted(set(assets) - {p.image_id for p in posts})
        if extras:
            issues.append(
                ValidationIssue(None, "image_id", str(extras[:30]), "import.unused_image",
                                f"Unused image IDs in ZIPs: {extras[:30]}", severity=Severity.WARNING)
            )

        # Validate Instagram aspect ratio compatibility (0.80 / 4:5 to 1.91:1)
        for p in posts:
            is_ig = any(getattr(pl, "value", str(pl)).lower() == "instagram" for pl in p.platforms)
            if is_ig and p.image_id in assets:
                info = assets[p.image_id]
                if info.width > 0 and info.height > 0:
                    ratio = info.width / info.height
                    if ratio < 0.79 or ratio > 1.93:
                        issues.append(
                            ValidationIssue(
                                None,
                                "image_id",
                                f"{p.image_id}.jpg",
                                "image.instagram_aspect_ratio",
                                f"Post {p.post_id} ({p.image_id}.jpg): Instagram requires an aspect ratio between 4:5 (0.80) and 1.91:1. "
                                f"Current image is {info.width}x{info.height} (ratio {ratio:.2f}). Meta will reject this post.",
                                severity=Severity.DANGER,
                            )
                        )

    if manifest_path is not None:
        issues.extend(_cross_check_manifest(manifest_path, len(posts)))

    issues.sort(key=lambda i: (_SEVERITY_ORDER.get(i.severity, 9), i.row or 0))
    return result


def _cross_check_manifest(manifest_path: str | Path, row_count: int) -> list[ValidationIssue]:
    import json

    issues: list[ValidationIssue] = []
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return [ValidationIssue(None, "manifest", "", "manifest.unreadable", f"Cannot read manifest: {exc}")]
    if manifest.get("schema_version") != "1.7":
        issues.append(ValidationIssue(None, "manifest", str(manifest.get("schema_version")), "manifest.schema", "Manifest schema_version must be \"1.7\""))
    if manifest.get("image_naming_pattern") != "{image_id}.jpg":
        issues.append(ValidationIssue(None, "manifest", str(manifest.get("image_naming_pattern")), "manifest.naming", "Manifest image_naming_pattern must be {image_id}.jpg"))
    if manifest.get("enabled_default") is not False:
        issues.append(ValidationIssue(None, "manifest", str(manifest.get("enabled_default")), "manifest.enabled_default", "Manifest enabled_default must be boolean false"))
    if manifest.get("post_count") not in (None, row_count):
        issues.append(ValidationIssue(None, "manifest", str(manifest.get("post_count")), "manifest.count", "Manifest post_count differs from plan row count", severity=Severity.WARNING))
    return issues
