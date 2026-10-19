"""Versioned caption / media / quota policy registry (PRD §8).

Values are conservative application policy pinned to a provider API version. They are NOT
permament provider guarantees: Phase 0 and publish-time checks re-verify them live. Changing
a policy means bumping the version string here and updating tests.
"""
from __future__ import annotations

from dataclasses import dataclass

from ...domain.enums import Platform


@dataclass(frozen=True)
class MediaPolicy:
    version: str
    platform: Platform
    max_caption_chars: int
    max_hashtags: int
    max_image_bytes: int
    min_aspect: float          # width / height
    max_aspect: float
    supported_mime: frozenset[str]
    media_mode: str = "single_image_feed"

    def aspect_ok(self, width: int, height: int) -> bool:
        if width <= 0 or height <= 0:
            return False
        ratio = width / height
        return self.min_aspect - 1e-6 <= ratio <= self.max_aspect + 1e-6

    def caption_ok(self, caption: str) -> bool:
        return len(caption) <= self.max_caption_chars


INSTAGRAM_V1_7 = MediaPolicy(
    version="instagram-2026.10",
    platform=Platform.INSTAGRAM,
    max_caption_chars=2200,
    max_hashtags=5,
    max_image_bytes=8 * 1024 * 1024,
    min_aspect=0.8,     # 4:5
    max_aspect=1.91,
    supported_mime=frozenset({"image/jpeg"}),
)

FACEBOOK_V1_7 = MediaPolicy(
    version="facebook-2026.10",
    platform=Platform.FACEBOOK,
    max_caption_chars=63206,
    max_hashtags=30,
    max_image_bytes=10 * 1024 * 1024,
    min_aspect=0.5,
    max_aspect=3.0,
    supported_mime=frozenset({"image/jpeg", "image/png"}),
)

_POLICIES = {
    Platform.INSTAGRAM: INSTAGRAM_V1_7,
    Platform.FACEBOOK: FACEBOOK_V1_7,
}


def get_policy(platform: Platform) -> MediaPolicy:
    return _POLICIES[platform]


def all_policies() -> dict[Platform, MediaPolicy]:
    return dict(_POLICIES)
