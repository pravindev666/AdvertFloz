"""ZIP + image validation (FR-006, PRD §8 ZIP rules).

Flat archives only. Defends against Zip Slip, symlinks, nested directories/archives, zip
bombs, hidden OS metadata, renamed non-JPEG bytes and range/duplicate mismatches. Nothing is
ever executed, and extraction stays inside a caller-provided sandbox.
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ...domain.models import ValidationIssue
from ...domain.validation_rules import IMAGE_FILENAME_RE, Severity, parse_zip_range

try:
    from PIL import Image  # type: ignore

    _PIL_AVAILABLE = True
except Exception:  # pragma: no cover
    _PIL_AVAILABLE = False

JPEG_MAGIC = b"\xff\xd8\xff"
#: Max compression ratio allowed before we treat an entry as a potential zip bomb.
MAX_COMPRESSION_RATIO = 200


@dataclass
class AssetInfo:
    image_id: int
    filename: str
    sha256: str
    byte_size: int
    width: int = 0
    height: int = 0


@dataclass
class ZipInspection:
    zip_name: str
    assets: dict[int, AssetInfo] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)
    expanded_bytes: int = 0

    @property
    def blocking(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.is_blocking]


def _issue(field_name: str, value: str, rule: str, message: str, severity: Severity = Severity.DANGER) -> ValidationIssue:
    text = str(value)
    shown = text if len(text) <= 60 else text[:60] + "…"
    return ValidationIssue(row=None, field=field_name, value=shown, rule=rule, message=message, severity=severity)


def _decode_dimensions(data: bytes) -> tuple[int, int, bool]:
    """Return (width, height, decoded_ok) using a real decoder when available."""
    if not _PIL_AVAILABLE:
        return 0, 0, False
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()  # detects truncated/corrupt files
        with Image.open(io.BytesIO(data)) as img:
            return int(img.width), int(img.height), True
    except Exception:
        return 0, 0, False


def inspect_zip(path: str | Path, *, max_image_bytes: int, max_expanded_bytes: int) -> ZipInspection:
    path = Path(path)
    inspection = ZipInspection(zip_name=path.name)
    if not path.is_file():
        inspection.issues.append(_issue("zip", path.name, "zip.missing", "ZIP part not found"))
        return inspection
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        inspection.issues.append(_issue("zip", path.name, "zip.invalid", "Not a valid ZIP archive"))
        return inspection

    intended_range: tuple[int, int] | None = None
    with archive:
        for info in archive.infolist():
            name = info.filename
            posix = PurePosixPath(name)

            if info.is_dir():
                inspection.issues.append(_issue("zip", name, "zip.dir", "Directories are not allowed; ZIP must be flat"))
                continue
            if "\\" in name or posix.is_absolute() or ".." in posix.parts or len(posix.parts) != 1:
                inspection.issues.append(_issue("zip", name, "zip.traversal", "Unsafe or non-flat path (traversal/symlink)"))
                continue
            mode = (info.external_attr >> 16) & 0xF000
            if mode == 0xA000:
                inspection.issues.append(_issue("zip", name, "zip.symlink", "Symlinks are not allowed"))
                continue
            if name.startswith("__MACOSX") or name in {".DS_Store", "Thumbs.db", "desktop.ini"} or name.startswith("._"):
                inspection.issues.append(_issue("zip", name, "zip.metadata", "Hidden OS metadata is not allowed"))
                continue
            if not IMAGE_FILENAME_RE.fullmatch(name):
                inspection.issues.append(
                    _issue("zip", name, "zip.filename",
                           "Expected a flat numeric root JPEG such as 42.jpg (no leading zeros, no folder)")
                )
                continue

            image_id = int(name[:-4])
            inspection.expanded_bytes += info.file_size
            if info.file_size > max_image_bytes:
                inspection.issues.append(_issue(name, name, "zip.image_size", "Asset exceeds the configured image byte limit"))
                continue
            if inspection.expanded_bytes > max_expanded_bytes:
                inspection.issues.append(_issue("zip", path.name, "zip.expanded", "Total expanded bytes exceed the configured limit"))
                break
            if info.compress_size > 0 and info.file_size / max(1, info.compress_size) > MAX_COMPRESSION_RATIO:
                inspection.issues.append(_issue(name, name, "zip.bomb", "Suspicious compression ratio (possible zip bomb)"))
                continue
            if image_id in inspection.assets:
                inspection.issues.append(_issue(name, name, "zip.duplicate", f"Duplicate image ID {image_id}"))
                continue

            try:
                data = archive.read(info)
            except Exception as exc:
                inspection.issues.append(_issue(name, name, "zip.read", f"Cannot read asset: {exc}"))
                continue

            if not data.startswith(JPEG_MAGIC):
                inspection.issues.append(_issue(name, name, "image.not_jpeg", "Filename says JPG but bytes are not JPEG"))
                continue
            width, height, decoded = _decode_dimensions(data)
            if _PIL_AVAILABLE and not decoded:
                inspection.issues.append(_issue(name, name, "image.undecodable", "JPEG failed to decode"))
                continue

            inspection.assets[image_id] = AssetInfo(
                image_id=image_id, filename=name, sha256=hashlib.sha256(data).hexdigest(),
                byte_size=len(data), width=width, height=height,
            )

        intended_range = parse_zip_range(path.name)

    if intended_range is not None:
        lo, hi = intended_range
        expected = set(range(lo, hi + 1))
        if set(inspection.assets) != expected:
            inspection.issues.append(
                _issue("zip", path.name, "zip.range",
                       f"Archive name range {lo:03d}-{hi:03d} does not match contained image IDs")
            )

    return inspection


def merge_inspections(inspections: list[ZipInspection]) -> tuple[dict[int, AssetInfo], list[ValidationIssue]]:
    """Combine parts into one global ID namespace, flagging cross-part duplicates."""
    merged: dict[int, AssetInfo] = {}
    issues: list[ValidationIssue] = []
    for inspection in inspections:
        issues.extend(inspection.issues)
        for image_id, asset in inspection.assets.items():
            if image_id in merged:
                issues.append(
                    _issue("image_id", str(image_id), "zip.duplicate_cross",
                           f"Duplicate image ID {image_id} across ZIP parts")
                )
                continue
            merged[image_id] = asset
    return merged, issues
