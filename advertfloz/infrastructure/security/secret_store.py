"""Secret access by name.

Resolution order: OS keyring (when available) → environment → Streamlit secrets (when the
app passes them in). Never returns a value to the UI layer for display; callers use it only
to configure a provider client or crypto primitive.
"""
from __future__ import annotations

import os

try:  # optional
    import keyring  # type: ignore

    _KEYRING = True
except Exception:  # pragma: no cover - keyring is optional
    _KEYRING = False

SERVICE_NAME = "advertfloz"


def get_secret(name: str, fallback_streamlit: dict | None = None) -> str:
    if _KEYRING:
        try:
            value = keyring.get_password(SERVICE_NAME, name)
            if value:
                return value
        except Exception:  # pragma: no cover
            pass
    if name in os.environ and os.environ[name]:
        return os.environ[name]
    if fallback_streamlit and name in fallback_streamlit:
        return str(fallback_streamlit[name])
    return ""


def has_secret(name: str, fallback_streamlit: dict | None = None) -> bool:
    return bool(get_secret(name, fallback_streamlit))
