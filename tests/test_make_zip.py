"""Tests for advertfloz.tools.make_zip (Auto-ZIP Batch Creator)."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from advertfloz.tools.make_zip import ZipResult, create_campaign_zip


# Minimal valid JPEG: SOI marker + minimal data
_JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 100


@pytest.fixture()
def image_folder(tmp_path: Path) -> Path:
    """Create a temp folder with numbered JPEG files 1.jpg through 5.jpg."""
    for i in range(1, 6):
        (tmp_path / f"{i}.jpg").write_bytes(_JPEG_BYTES)
    return tmp_path


def test_create_zip_success(image_folder: Path, tmp_path: Path) -> None:
    output = tmp_path / "test_output.zip"
    result = create_campaign_zip(image_folder, output, range_start=1, range_end=5)
    assert result.ok
    assert result.image_count == 5
    assert result.zip_path == output
    assert output.exists()

    # Verify ZIP contents are flat (no subdirectories)
    with zipfile.ZipFile(output) as zf:
        names = sorted(zf.namelist())
        assert names == ["1.jpg", "2.jpg", "3.jpg", "4.jpg", "5.jpg"]


def test_create_zip_auto_detect_range(image_folder: Path) -> None:
    result = create_campaign_zip(image_folder)
    assert result.ok
    assert result.image_count == 5


def test_missing_images(image_folder: Path) -> None:
    # Remove image 3.jpg
    (image_folder / "3.jpg").unlink()
    result = create_campaign_zip(image_folder, range_start=1, range_end=5)
    assert not result.ok
    assert any("3.jpg" in e for e in result.errors)


def test_invalid_jpeg(image_folder: Path) -> None:
    # Replace image 2.jpg with non-JPEG data
    (image_folder / "2.jpg").write_bytes(b"not a jpeg file at all")
    result = create_campaign_zip(image_folder, range_start=1, range_end=5)
    assert not result.ok
    assert any("not a valid JPEG" in e for e in result.errors)


def test_empty_folder(tmp_path: Path) -> None:
    result = create_campaign_zip(tmp_path)
    assert not result.ok
    assert any("No numbered" in e for e in result.errors)


def test_nonexistent_folder(tmp_path: Path) -> None:
    result = create_campaign_zip(tmp_path / "does_not_exist")
    assert not result.ok
    assert any("does not exist" in e for e in result.errors)


def test_extra_files_warning(image_folder: Path) -> None:
    # Add an extra file outside the specified range
    (image_folder / "99.jpg").write_bytes(_JPEG_BYTES)
    result = create_campaign_zip(image_folder, range_start=1, range_end=5)
    assert result.ok
    assert result.image_count == 5
    assert any("Extra files" in w for w in result.warnings)


def test_partial_range(image_folder: Path) -> None:
    result = create_campaign_zip(image_folder, range_start=2, range_end=4)
    assert result.ok
    assert result.image_count == 3
