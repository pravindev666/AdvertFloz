"""UTM generation from stable, non-personal campaign fields only (PRD §12).

Never place personal or sensitive data in UTM parameters. Only source, medium, campaign
tag and post_id are used.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SAFE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")

#: Substrings that must never appear in a UTM value (defensive; blocks accidental PII).
_FORBIDDEN_HINTS = ("@", " ", "?", "#", "/", "\\", "+", "=")


def _is_safe_token(value: str) -> bool:
    return bool(value) and all(ch in SAFE_CHARS for ch in value)


def build_utm(
    destination_url: str,
    campaign_tag: str,
    post_id: str,
    source: str = "advertfloz",
    medium: str = "social",
) -> str:
    """Return ``destination_url`` with stable UTM parameters appended.

    Raises ValueError if the destination is not HTTPS or any token is unsafe.
    """
    if not destination_url.startswith("https://"):
        raise ValueError("destination_url must be HTTPS")
    for name, value in (("campaign_tag", campaign_tag), ("post_id", post_id), ("source", source), ("medium", medium)):
        if any(hint in value for hint in _FORBIDDEN_HINTS) or not _is_safe_token(value):
            raise ValueError(f"unsafe UTM value for {name}: {value!r}")

    parsed = urlparse(destination_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "utm_source": source,
            "utm_medium": medium,
            "utm_campaign": campaign_tag,
            "utm_content": post_id,
        }
    )
    return urlunparse(parsed._replace(query=urlencode(query)))
