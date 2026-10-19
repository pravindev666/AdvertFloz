"""The supplied validators must agree with the fixtures (source-of-truth rule)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.support import make_image_zip

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_campaign_package_v1.7.py"
FIXTURES = Path(__file__).parent / "fixtures"

requires_pillow = pytest.mark.skipif(
    not (FIXTURES / "campaign_plan_template_v1.7.csv").exists(), reason="fixtures missing"
)


def run_validator(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        capture_output=True, text=True, cwd=ROOT,
    )


@requires_pillow
def test_valid_fixture_passes(tmp_path: Path):
    zip_path = make_image_zip(tmp_path / "advertfloz_images_001_003.zip", [1, 2, 3])
    result = run_validator(
        "--csv", str(FIXTURES / "AdvertFloz_fixture_valid_edge_cases_v1.7.csv"),
        "--zip", str(zip_path),
        "--manifest", str(FIXTURES / "campaign_manifest_template_v1.7.json"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


@requires_pillow
def test_invalid_fixture_fails_with_reasons(tmp_path: Path):
    # Supply only image 1 so referenced image 99 is missing, plus the fixture's own errors.
    zip_path = make_image_zip(tmp_path / "part.zip", [1])
    result = run_validator(
        "--csv", str(FIXTURES / "AdvertFloz_fixture_invalid_v1.7.csv"),
        "--zip", str(zip_path),
    )
    assert result.returncode == 1
    assert "ERROR:" in result.stdout
    combined = result.stdout
    assert "enabled" in combined
    assert "unknown IANA timezone" in combined


@requires_pillow
def test_png_renamed_jpg_is_rejected_by_validator(tmp_path: Path):
    from tests.support import make_zip

    zip_path = make_zip(tmp_path / "part.zip", {"1.jpg": b"\x89PNG\r\n\x1a\n" + b"0" * 32})
    result = run_validator(
        "--csv", str(FIXTURES / "campaign_plan_template_v1.7.csv"),
        "--zip", str(zip_path),
    )
    assert result.returncode == 1
    assert "not JPEG" in result.stdout
