"""Reusable test helpers (JPEG/ZIP/CSV builders) importable from any test module."""
from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import pytest

try:
    from PIL import Image

    _PIL = True
except Exception:  # pragma: no cover
    _PIL = False

requires_pillow = pytest.mark.skipif(not _PIL, reason="Pillow not installed")

PLAN_HEADER = (
    "post_id,scheduled_at,timezone,platforms,image_id,caption,enabled,campaign_tag,"
    "facebook_caption,instagram_caption,alt_text,destination_url,grace_minutes,"
    "ai_disclosure_status,notes"
)
PLAN_COLUMNS = PLAN_HEADER.split(",")


def make_jpeg_bytes(width: int = 64, height: int = 80, color=(80, 120, 200)) -> bytes:
    if not _PIL:
        raise RuntimeError("Pillow is required to synthesise JPEG test assets")
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()


def make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


def make_image_zip(path: Path, image_ids: list[int], *, width: int = 64, height: int = 80) -> Path:
    return make_zip(path, {f"{iid}.jpg": make_jpeg_bytes(width, height) for iid in image_ids})


def plan_row(post_id: str = "P001", **overrides) -> dict:
    ordinal = int(post_id[1:])
    row = {
        "post_id": post_id,
        "scheduled_at": overrides.pop("scheduled_at", f"2027-01-{min(ordinal, 28):02d}T09:00:00"),
        "timezone": "Asia/Kolkata",
        "platforms": "facebook",
        "image_id": str(ordinal),
        "caption": f"Caption for {post_id}",
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


def write_plan(path: Path, rows: list[dict], header: list[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = header or PLAN_COLUMNS
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path
