"""Contact sheet generation (FR-007).

Bounded thumbnails linked to post/image IDs for human quality review. Uses Pillow when
available; otherwise a text manifest is returned so the feature degrades visibly rather than
faking an image.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from ...domain.models import MediaAsset

try:
    from PIL import Image  # type: ignore

    _PIL_AVAILABLE = True
except Exception:  # pragma: no cover
    _PIL_AVAILABLE = False

DEFAULT_COLUMNS = 8
DEFAULT_THUMB = 160


@dataclass
class ContactSheetTile:
    image_id: int
    post_id: str
    filename: str
    production_state: str
    approved: bool


def tile_metadata(assets: list[MediaAsset], post_id_by_image: dict[int, str]) -> list[ContactSheetTile]:
    tiles = []
    for asset in sorted(assets, key=lambda a: a.image_id):
        tiles.append(
            ContactSheetTile(
                image_id=asset.image_id,
                post_id=post_id_by_image.get(asset.image_id, ""),
                filename=asset.filename,
                production_state=asset.production_state.value,
                approved=asset.approved,
            )
        )
    return tiles


def build_contact_sheet(
    media_paths: dict[int, Path],
    *,
    columns: int = DEFAULT_COLUMNS,
    thumb: int = DEFAULT_THUMB,
) -> bytes | None:
    """Render a montage PNG. Returns None when Pillow is unavailable.

    Memory is bounded: images are decoded one at a time and never all held as full-size
    bitmaps simultaneously beyond the single target canvas.
    """
    if not _PIL_AVAILABLE or not media_paths:
        return None
    ids = sorted(media_paths)
    rows = (len(ids) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * thumb, rows * thumb), (246, 248, 252))
    for index, image_id in enumerate(ids):
        try:
            with Image.open(media_paths[image_id]) as img:
                img = img.convert("RGB")
                img.thumbnail((thumb, thumb))
                x = (index % columns) * thumb + (thumb - img.width) // 2
                y = (index // columns) * thumb + (thumb - img.height) // 2
                canvas.paste(img, (x, y))
        except Exception:
            continue
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def render_text_manifest(tiles: list[ContactSheetTile]) -> str:
    lines = ["# Contact sheet manifest", "", "| image_id | post_id | filename | state | approved |", "|---|---|---|---|---|"]
    for tile in tiles:
        lines.append(f"| {tile.image_id} | {tile.post_id} | {tile.filename} | {tile.production_state} | {tile.approved} |")
    return "\n".join(lines)
