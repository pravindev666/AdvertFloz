"""Semantic color tokens (PRD §3.2).

Light and dark themes are defined once here. Components consume named tokens instead of
hard-coded colors, so both appearances stay consistent and testable.
"""
from __future__ import annotations

LIGHT = {
    "bg": "#F6F8FC",
    "surface": "#FFFFFF",
    "surface_alt": "#EEF2F7",
    "text": "#162033",
    "text_alt": "#64748B",
    "border": "#D9E1EC",
    "primary": "#4F46E5",
    "accent": "#0F766E",
    "success": "#166534",
    "success_surface": "#DCFCE7",
    "warning": "#9A3412",
    "warning_surface": "#FFEDD5",
    "danger": "#B91C1C",
    "danger_surface": "#FEE2E2",
    "info": "#1D4ED8",
    "info_surface": "#DBEAFE",
    "mono_bg": "#EEF2F7",
}

DARK = {
    "bg": "#0B1220",
    "surface": "#111B2C",
    "surface_alt": "#17243A",
    "text": "#E8EEF7",
    "text_alt": "#A3B1C6",
    "border": "#2B3A50",
    "primary": "#A5B4FC",
    "accent": "#5EEAD4",
    "success": "#86EFAC",
    "success_surface": "#123324",
    "warning": "#FDBA74",
    "warning_surface": "#3A2415",
    "danger": "#FCA5A5",
    "danger_surface": "#3B171C",
    "info": "#93C5FD",
    "info_surface": "#142C4D",
    "mono_bg": "#17243A",
}

#: Statuses map to a semantic tone; UI always renders an icon + label alongside the color so
#: status is never conveyed by color alone (NFR-09).
STATUS_TONE = {
    "PUBLISHED": "success",
    "SYNCED": "success",
    "QUEUED": "info",
    "SYNC_PENDING": "info",
    "PROCESSING_MEDIA": "info",
    "PUBLISHING": "info",
    "CLAIMED": "info",
    "APPROVED": "info",
    "READY_FOR_REVIEW": "info",
    "DRAFT": "neutral",
    "VALIDATION_BLOCKED": "warning",
    "FAILED_RETRYABLE": "warning",
    "MISSED": "warning",
    "PAUSED": "warning",
    "FAILED_PERMANENT": "danger",
    "UNKNOWN_OUTCOME": "danger",
    "CANCELLED": "neutral",
}

STATUS_ICON = {
    "PUBLISHED": "✔",
    "QUEUED": "◷",
    "CLAIMED": "◷",
    "PROCESSING_MEDIA": "◷",
    "PUBLISHING": "◷",
    "SYNCED": "✔",
    "SYNC_PENDING": "◷",
    "DRAFT": "○",
    "APPROVED": "◈",
    "READY_FOR_REVIEW": "◈",
    "VALIDATION_BLOCKED": "⚠",
    "FAILED_RETRYABLE": "↻",
    "FAILED_PERMANENT": "✖",
    "MISSED": "⏰",
    "PAUSED": "⏸",
    "UNKNOWN_OUTCOME": "❓",
    "CANCELLED": "⊘",
}


def get_tokens(dark: bool = False) -> dict:
    return DARK if dark else LIGHT


def tone_for(status: str) -> str:
    return STATUS_TONE.get(status, "neutral")


def icon_for(status: str) -> str:
    return STATUS_ICON.get(status, "•")
