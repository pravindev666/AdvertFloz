"""Auto-ZIP Batch Creator (FR-ZIP).

Takes a folder of AI-generated images, verifies they are valid JPEG files,
checks they follow the sequential ``1.jpg`` to ``N.jpg`` naming convention,
and produces a flat ZIP file ready for AdvertFloz campaign import.

Usage (CLI)::

    python -m advertfloz.tools.make_zip --folder ./my_images --output advertfloz_images.zip
    python -m advertfloz.tools.make_zip --folder ./my_images --range 1-30

Usage (library)::

    from advertfloz.tools.make_zip import create_campaign_zip
    result = create_campaign_zip(Path("./my_images"), Path("output.zip"), range_start=1, range_end=30)
"""
from __future__ import annotations

import argparse
import struct
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


# JPEG SOI marker (first two bytes of any valid JPEG)
_JPEG_SOI = b"\xff\xd8"
# Maximum allowed image size (10 MB) — same as PRD validation_rules
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
# Decompression bomb limit
_MAX_EXPANDED_BYTES = 50 * 1024 * 1024


@dataclass
class ZipResult:
    """Result of a ZIP creation attempt."""
    ok: bool = True
    zip_path: Path | None = None
    image_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_valid_jpeg(path: Path) -> bool:
    """Check if a file starts with the JPEG SOI marker."""
    try:
        with open(path, "rb") as f:
            header = f.read(2)
        return header == _JPEG_SOI
    except OSError:
        return False


def _check_image_size(path: Path) -> str | None:
    """Return an error string if the file exceeds size limits."""
    size = path.stat().st_size
    if size > _MAX_IMAGE_BYTES:
        return f"{path.name}: {size:,} bytes exceeds {_MAX_IMAGE_BYTES:,} byte limit"
    if size == 0:
        return f"{path.name}: file is empty (0 bytes)"
    return None


def create_campaign_zip(
    folder: Path,
    output: Path | None = None,
    range_start: int = 1,
    range_end: int | None = None,
) -> ZipResult:
    """Create a flat campaign ZIP from a folder of numbered JPEG images.

    Parameters
    ----------
    folder:
        Directory containing ``1.jpg``, ``2.jpg``, ... image files.
    output:
        Path for the output ZIP file. Defaults to ``<folder>/advertfloz_images_<start>_<end>.zip``.
    range_start:
        First expected image number (inclusive). Default 1.
    range_end:
        Last expected image number (inclusive). If None, auto-detects from folder.

    Returns
    -------
    ZipResult with success/failure info, path, and any errors/warnings.
    """
    result = ZipResult()

    if not folder.is_dir():
        result.ok = False
        result.errors.append(f"Folder does not exist: {folder}")
        return result

    # Discover all .jpg files in the folder
    jpg_files: dict[int, Path] = {}
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() in (".jpg", ".jpeg") and f.stem.isdigit():
            num = int(f.stem)
            jpg_files[num] = f

    if not jpg_files:
        result.ok = False
        result.errors.append(f"No numbered .jpg files found in {folder}")
        return result

    # Auto-detect range if not specified
    if range_end is None:
        range_end = max(jpg_files.keys())
    expected = set(range(range_start, range_end + 1))

    # Check for missing images
    found = set(jpg_files.keys()) & expected
    missing = expected - found
    if missing:
        missing_str = ", ".join(f"{n}.jpg" for n in sorted(missing)[:10])
        suffix = f" ... and {len(missing) - 10} more" if len(missing) > 10 else ""
        result.errors.append(f"Missing {len(missing)} image(s): {missing_str}{suffix}")
        result.ok = False

    # Validate each image in range
    valid_files: list[tuple[int, Path]] = []
    total_bytes = 0
    for num in sorted(found):
        path = jpg_files[num]

        # Check file size
        size_err = _check_image_size(path)
        if size_err:
            result.errors.append(size_err)
            result.ok = False
            continue

        # Check JPEG header
        if not _is_valid_jpeg(path):
            result.errors.append(f"{path.name}: not a valid JPEG file (bad SOI header)")
            result.ok = False
            continue

        total_bytes += path.stat().st_size
        valid_files.append((num, path))

    # Decompression bomb check
    if total_bytes > _MAX_EXPANDED_BYTES:
        result.warnings.append(
            f"Total image size is {total_bytes:,} bytes ({total_bytes / 1024 / 1024:.1f} MB). "
            f"This exceeds the recommended {_MAX_EXPANDED_BYTES / 1024 / 1024:.0f} MB limit."
        )

    # Extra files warning
    extra = set(jpg_files.keys()) - expected
    if extra:
        extra_str = ", ".join(f"{n}.jpg" for n in sorted(extra)[:5])
        result.warnings.append(f"Extra files outside range {range_start}-{range_end} ignored: {extra_str}")

    if not result.ok:
        return result

    # Build output path
    if output is None:
        output = folder / f"advertfloz_images_{range_start:03d}_{range_end:03d}.zip"

    # Create flat ZIP (no subdirectories)
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as zf:
            for num, path in valid_files:
                # Store as flat filename: 1.jpg, 2.jpg, etc. (no subfolder)
                zf.write(path, arcname=f"{num}.jpg")
    except OSError as e:
        result.ok = False
        result.errors.append(f"Failed to create ZIP: {e}")
        return result

    result.zip_path = output
    result.image_count = len(valid_files)
    return result


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="advertfloz-make-zip",
        description=(
            "Auto-ZIP Batch Creator: Validates images and creates a flat ZIP "
            "ready for AdvertFloz campaign import."
        ),
    )
    parser.add_argument(
        "--folder", "-f",
        type=Path,
        required=True,
        help="Directory containing numbered .jpg images (1.jpg, 2.jpg, ...)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output ZIP file path (default: auto-generated in the source folder)",
    )
    parser.add_argument(
        "--range", "-r",
        type=str,
        default=None,
        help="Image range, e.g. '1-30' for images 1.jpg through 30.jpg",
    )

    args = parser.parse_args()

    range_start = 1
    range_end = None
    if args.range:
        parts = args.range.split("-")
        if len(parts) != 2:
            print(f"ERROR: --range must be in format 'START-END', got '{args.range}'", file=sys.stderr)
            sys.exit(1)
        range_start, range_end = int(parts[0]), int(parts[1])

    print(f"Scanning folder: {args.folder.resolve()}")
    result = create_campaign_zip(args.folder, args.output, range_start, range_end)

    for warning in result.warnings:
        print(f"  WARNING: {warning}")

    if not result.ok:
        print("\nFAILED — errors found:")
        for error in result.errors:
            print(f"  ERROR: {error}")
        sys.exit(1)

    print(f"\n✓ SUCCESS: Created {result.zip_path}")
    print(f"  Images: {result.image_count}")
    print(f"  Size: {result.zip_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
