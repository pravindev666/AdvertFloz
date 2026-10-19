"""Compact summary strip for the Overview screen (PRD §4.2).

Each value is derived from stored state. ``link_page`` links to the relevant screen when the
navigation context supports it.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape

from .nav import page_link


@dataclass
class SummaryItem:
    label: str
    value: str
    tone: str = "neutral"
    link_page: str = ""


def summary_strip(st, items: list[SummaryItem], columns: int = 4) -> None:
    """Render a responsive strip of summary cells."""
    rows = [items[i:i + columns] for i in range(0, len(items), columns)]
    for row in rows:
        cols = st.columns(len(row))
        for col, item in zip(cols, row, strict=False):
            with col:
                html = (
                    f'<div class="afz-panel" style="margin-bottom:6px">'
                    f'<div class="afz-summary-label">{escape(item.label)}</div>'
                    f'<div class="afz-summary-value afz-tone-{item.tone}">{escape(item.value)}</div>'
                    f"</div>"
                )
                st.markdown(html, unsafe_allow_html=True)
                if item.link_page:
                    page_link(st, item.link_page, "Open →", icon=":material/arrow_forward:")
