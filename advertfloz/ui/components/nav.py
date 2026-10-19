"""Navigation helpers that never break a page render.

``st.page_link``/``st.switch_page`` require the target to be registered with ``st.navigation``.
These wrappers degrade to a no-op (or a plain caption) when that is not the case, so a page never
crashes because of a navigation affordance.
"""
from __future__ import annotations


def page_link(st, path: str, label: str, icon: str | None = None) -> bool:
    try:
        st.page_link(path, label=label, icon=icon) if icon else st.page_link(path, label=label)
        return True
    except Exception:  # pragma: no cover - depends on navigation context
        return False


def switch_page(st, path: str) -> bool:
    try:
        st.switch_page(path)
        return True
    except Exception:  # pragma: no cover - depends on navigation context
        st.caption(f"Open: {label_for(path)}")
        return False


def label_for(path: str) -> str:
    return path.rsplit("/", 1)[-1].removesuffix(".py").replace("_", " ").title()
