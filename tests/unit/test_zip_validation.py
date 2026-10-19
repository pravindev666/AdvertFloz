"""Unit tests for ZIP/image validation defences (FR-006, fault register)."""
from __future__ import annotations

from pathlib import Path

from advertfloz.infrastructure.storage.zip_validation import inspect_zip, merge_inspections
from tests.support import make_image_zip, make_jpeg_bytes, make_zip, requires_pillow

LIMITS = dict(max_image_bytes=8 * 1024 * 1024, max_expanded_bytes=1_000_000_000)


@requires_pillow
def test_valid_flat_zip_passes(tmp_path: Path):
    path = make_image_zip(tmp_path / "advertfloz_images_001_003.zip", [1, 2, 3])
    result = inspect_zip(path, **LIMITS)
    assert not result.blocking
    assert sorted(result.assets) == [1, 2, 3]
    assert result.assets[1].width > 0


@requires_pillow
def test_range_mismatch_blocks(tmp_path: Path):
    path = make_image_zip(tmp_path / "advertfloz_images_001_005.zip", [1, 2, 3])
    result = inspect_zip(path, **LIMITS)
    assert any(i.rule == "zip.range" for i in result.blocking)


def test_png_renamed_jpg_blocks(tmp_path: Path):
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    path = make_zip(tmp_path / "advertfloz_images_001_001.zip", {"1.jpg": png_bytes})
    result = inspect_zip(path, **LIMITS)
    assert any(i.rule == "image.not_jpeg" for i in result.blocking)


def test_traversal_and_nested_blocks(tmp_path: Path):
    path = make_zip(tmp_path / "part.zip", {"../evil.jpg": make_jpeg_bytes(), "1.jpg": make_jpeg_bytes()})
    result = inspect_zip(path, **LIMITS)
    assert any(i.rule == "zip.traversal" for i in result.blocking)


def test_leading_zero_and_prefix_block(tmp_path: Path):
    path = make_zip(tmp_path / "part.zip", {"042.jpg": make_jpeg_bytes(), "P001.jpg": make_jpeg_bytes()})
    result = inspect_zip(path, **LIMITS)
    assert any(i.rule == "zip.filename" for i in result.blocking)


def test_hidden_metadata_blocks(tmp_path: Path):
    path = make_zip(tmp_path / "part.zip", {"__MACOSX/._1.jpg": b"", "1.jpg": make_jpeg_bytes()})
    result = inspect_zip(path, **LIMITS)
    assert any(i.rule in {"zip.metadata", "zip.traversal"} for i in result.blocking)


def test_duplicate_ids_across_parts_block(tmp_path: Path):
    a = make_image_zip(tmp_path / "a.zip", [1])
    b = make_image_zip(tmp_path / "b.zip", [1])
    merged, issues = merge_inspections([inspect_zip(a, **LIMITS), inspect_zip(b, **LIMITS)])
    assert len(merged) == 1
    assert sum(1 for i in issues if i.rule == "zip.duplicate_cross") == 1


def test_per_asset_size_limit(tmp_path: Path):
    path = make_image_zip(tmp_path / "part.zip", [1])
    result = inspect_zip(path, max_image_bytes=10, max_expanded_bytes=10**9)
    assert any(i.rule == "zip.image_size" for i in result.blocking)
