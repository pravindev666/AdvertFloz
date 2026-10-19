"""Local media store and safe extraction sandbox.

Extraction never writes to arbitrary paths: only validated, flat, numeric JPEG entries are
written into a per-import sandbox directory, keyed by verified image_id.
"""
from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

from .zip_validation import JPEG_MAGIC, inspect_zip


class StoreError(RuntimeError):
    pass


class LocalMediaStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def media_path(self, image_id: int) -> Path:
        return self.root / f"{image_id}.jpg"

    def write_asset(self, image_id: int, data: bytes) -> tuple[Path, str]:
        if not data.startswith(JPEG_MAGIC):
            raise StoreError(f"image {image_id} is not JPEG")
        digest = hashlib.sha256(data).hexdigest()
        path = self.media_path(image_id)
        path.write_bytes(data)
        return path, digest

    def exists(self, image_id: int) -> bool:
        return self.media_path(image_id).is_file()

    def read(self, image_id: int) -> bytes:
        return self.media_path(image_id).read_bytes()

    def checksum(self, image_id: int) -> str:
        return hashlib.sha256(self.read(image_id)).hexdigest()

    def verify_checksum(self, image_id: int, expected: str) -> bool:
        return self.exists(image_id) and self.checksum(image_id) == expected

    def usage_bytes(self) -> int:
        return sum(f.stat().st_size for f in self.root.glob("*.jpg"))


def extract_validated(zip_path: str | Path, sandbox: str | Path, *, max_image_bytes: int, max_expanded_bytes: int) -> list[int]:
    """Extract only validated flat JPEG entries into ``sandbox``. Returns written image IDs.

    Raises StoreError if the archive has any blocking issue, so a partial/bad import cannot
    silently proceed into the sandbox.
    """
    inspection = inspect_zip(zip_path, max_image_bytes=max_image_bytes, max_expanded_bytes=max_expanded_bytes)
    if inspection.blocking:
        raise StoreError("archive has blocking validation errors; refusing to extract")
    sandbox_path = Path(sandbox)
    sandbox_path.mkdir(parents=True, exist_ok=True)
    written: list[int] = []
    with zipfile.ZipFile(zip_path) as archive:
        for image_id in sorted(inspection.assets):
            info = archive.getinfo(f"{image_id}.jpg")
            data = archive.read(info)
            (sandbox_path / f"{image_id}.jpg").write_bytes(data)
            written.append(image_id)
    return written


def cleanup_sandbox(sandbox: str | Path) -> None:
    path = Path(sandbox)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
