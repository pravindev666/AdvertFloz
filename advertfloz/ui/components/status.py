"""Status badges and chips: icon + label + color, so status is never color-only (NFR-09)."""
from __future__ import annotations

from html import escape

from ..theme.tokens import icon_for, tone_for


def status_badge(status: str) -> str:
    """Return HTML for a status badge. Always includes a glyph and the literal status text."""
    tone = tone_for(status)
    icon = icon_for(status)
    label = escape(status.replace("_", " ").title())
    return f'<span class="afz-badge afz-tone-{tone}"><span aria-hidden="true">{icon}</span>{label}</span>'


def chip(text: str, tone: str = "neutral") -> str:
    return f'<span class="afz-chip afz-tone-{tone}">{escape(text)}</span>'


def platform_chips(platforms: tuple) -> str:
    return " ".join(chip(getattr(p, "label", str(p)), "info") for p in platforms)
