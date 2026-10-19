"""Central configuration for AdvertFloz.

Values come from environment variables and (when running under Streamlit) Streamlit
secrets. Secret values are never logged, echoed to the UI, or returned by ``redacted()``.

This module deliberately avoids importing Streamlit at module import time so that CLI
tools, the local scheduler and tests can use it without a Streamlit runtime.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional, so the package works without dotenv installed
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass

VALID_MODES = {"local", "demo", "remote"}

#: Names of configuration values that must never appear in logs, errors or the UI.
SECRET_KEYS = frozenset(
    {
        "META_APP_SECRET",
        "TOKEN_ENCRYPTION_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_WEBHOOK_SECRET",
        "WORKER_SERVICE_KEY",
        "ADVERTFLOZ_OIDC_CLIENT_SECRET",
        "ADVERTFLOZ_ADMIN_PASSWORD",
        "ADVERTFLOZ_MASTER_PASSWORD",
    }
)


def _st_secrets() -> dict:
    """Best-effort read of Streamlit secrets without importing Streamlit eagerly."""
    try:
        import streamlit as st  # noqa: PLC0415

        # st.secrets raises if no secrets file exists.
        try:
            return {k: st.secrets[k] for k in st.secrets}  # type: ignore[attr-defined]
        except Exception:
            return {}
    except Exception:
        return {}


def _get(key: str, secrets: dict, default: str = "") -> str:
    if key in os.environ:
        return os.environ[key]
    if key in secrets:
        return str(secrets[key])
    return default


def _get_bool(key: str, secrets: dict, default: bool = False) -> bool:
    raw = _get(key, secrets, "")
    if raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(key: str, secrets: dict, default: int) -> int:
    raw = _get(key, secrets, "")
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    mode: str = "local"
    db_path: Path = field(default_factory=lambda: Path("data/advertfloz.sqlite"))
    default_timezone: str = "Asia/Kolkata"

    hosted: bool = False
    operator_allowlist: tuple[str, ...] = ()
    oidc_issuer: str = ""
    oidc_client_id: str = ""

    oauth_callback_host: str = "127.0.0.1"
    oauth_callback_port: int = 8765
    control_plane_url: str = "http://localhost:8501"

    meta_app_id: str = ""
    meta_graph_version: str = "v21.0"
    meta_oauth_redirect_uri: str = "http://localhost:8765/oauth/meta/callback"

    token_encryption_key_id: str = "k1"

    telegram_allowed_chat_id: str = ""
    worker_base_url: str = ""
    worker_service_key: str = ""
    media_base_url: str = ""

    max_image_bytes: int = 8 * 1024 * 1024
    max_expanded_bytes: int = 1_000_000_000
    max_archive_bytes: int = 250 * 1024 * 1024

    # Secrets held only in memory; never returned by redacted().
    _secrets: dict = field(default_factory=dict, repr=False, compare=False)

    # ------------------------------------------------------------------ helpers
    @property
    def meta_app_configured(self) -> bool:
        return bool(self.meta_app_id and self._secrets.get("META_APP_SECRET"))

    @property
    def token_key_present(self) -> bool:
        return bool(self._secrets.get("TOKEN_ENCRYPTION_KEY"))

    @property
    def telegram_configured(self) -> bool:
        return bool(self._secrets.get("TELEGRAM_BOT_TOKEN") and self.telegram_allowed_chat_id)

    @property
    def admin_password_configured(self) -> bool:
        return bool(self._secrets.get("ADVERTFLOZ_ADMIN_PASSWORD"))

    @property
    def worker_configured(self) -> bool:
        return bool(self.worker_base_url and self.worker_service_key)

    def binding_is_loopback(self) -> bool:
        return self.oauth_callback_host in {"127.0.0.1", "localhost", "::1"}

    def hosted_auth_ready(self) -> bool:
        """Fail closed: hosted control planes must have an allowlist and an IdP or admin password."""
        return bool((self.oidc_issuer and self.operator_allowlist) or self.admin_password_configured)

    def redacted(self) -> dict:
        """A safe-to-display view: booleans and non-secret scalars only."""
        return {
            "mode": self.mode,
            "db_path": str(self.db_path),
            "default_timezone": self.default_timezone,
            "hosted": self.hosted,
            "admin_password_configured": self.admin_password_configured,
            "operator_allowlist_count": len(self.operator_allowlist),
            "oauth_callback": f"{self.oauth_callback_host}:{self.oauth_callback_port}",
            "meta_graph_version": self.meta_graph_version,
            "meta_app_configured": self.meta_app_configured,
            "meta_oauth_redirect_uri": self.meta_oauth_redirect_uri,
            "token_encryption_configured": self.token_key_present,
            "token_encryption_key_id": self.token_encryption_key_id,
            "telegram_configured": self.telegram_configured,
            "worker_configured": self.worker_configured,
            "max_image_bytes": self.max_image_bytes,
            "max_expanded_bytes": self.max_expanded_bytes,
            "max_archive_bytes": self.max_archive_bytes,
        }

    def secret(self, key: str) -> str:
        """Explicit accessor for a secret. Callers must not log or echo the result."""
        return self._secrets.get(key, "")


def load_settings(secrets: dict | None = None) -> Settings:
    secrets = dict(secrets) if secrets is not None else _st_secrets()

    mode = _get("ADVERTFLOZ_MODE", secrets, "local").strip().lower()
    if mode not in VALID_MODES:
        mode = "local"

    allowlist = tuple(
        part.strip() for part in _get("ADVERTFLOZ_OPERATOR_ALLOWLIST", secrets).split(",") if part.strip()
    )

    admin_pass = _get("ADVERTFLOZ_ADMIN_PASSWORD", secrets) or _get("ADVERTFLOZ_MASTER_PASSWORD", secrets) or _get("ADVERTFLOZ_PASSWORD", secrets)

    secret_values = {
        "META_APP_SECRET": _get("META_APP_SECRET", secrets),
        "TOKEN_ENCRYPTION_KEY": _get("TOKEN_ENCRYPTION_KEY", secrets),
        "TELEGRAM_BOT_TOKEN": _get("TELEGRAM_BOT_TOKEN", secrets),
        "TELEGRAM_WEBHOOK_SECRET": _get("TELEGRAM_WEBHOOK_SECRET", secrets),
        "WORKER_SERVICE_KEY": _get("WORKER_SERVICE_KEY", secrets),
        "ADVERTFLOZ_OIDC_CLIENT_SECRET": _get("ADVERTFLOZ_OIDC_CLIENT_SECRET", secrets),
        "ADVERTFLOZ_ADMIN_PASSWORD": admin_pass,
    }

    return Settings(
        mode=mode,
        db_path=Path(_get("ADVERTFLOZ_DB_PATH", secrets, "data/advertfloz.sqlite")),
        default_timezone=_get("ADVERTFLOZ_DEFAULT_TIMEZONE", secrets, "Asia/Kolkata"),
        hosted=_get_bool("ADVERTFLOZ_HOSTED", secrets, False),
        operator_allowlist=allowlist,
        oidc_issuer=_get("ADVERTFLOZ_OIDC_ISSUER", secrets),
        oidc_client_id=_get("ADVERTFLOZ_OIDC_CLIENT_ID", secrets),
        oauth_callback_host=_get("OAUTH_CALLBACK_HOST", secrets, "127.0.0.1"),
        oauth_callback_port=_get_int("OAUTH_CALLBACK_PORT", secrets, 8765),
        control_plane_url=_get("ADVERTFLOZ_CONTROL_PLANE_URL", secrets, "http://localhost:8501"),
        meta_app_id=_get("META_APP_ID", secrets),
        meta_graph_version=_get("META_GRAPH_VERSION", secrets, "v21.0"),
        meta_oauth_redirect_uri=_get(
            "META_OAUTH_REDIRECT_URI", secrets, "http://localhost:8765/oauth/meta/callback"
        ),
        token_encryption_key_id=_get("TOKEN_ENCRYPTION_KEY_ID", secrets, "k1"),
        telegram_allowed_chat_id=_get("TELEGRAM_ALLOWED_CHAT_ID", secrets),
        worker_base_url=_get("WORKER_BASE_URL", secrets),
        worker_service_key=_get("WORKER_SERVICE_KEY", secrets),
        media_base_url=_get("ADVERTFLOZ_MEDIA_BASE_URL", secrets),
        max_image_bytes=_get_int("ADVERTFLOZ_MAX_IMAGE_BYTES", secrets, 8 * 1024 * 1024),
        max_expanded_bytes=_get_int("ADVERTFLOZ_MAX_EXPANDED_BYTES", secrets, 1_000_000_000),
        max_archive_bytes=_get_int("ADVERTFLOZ_MAX_ARCHIVE_BYTES", secrets, 250 * 1024 * 1024),
        _secrets=secret_values,
    )


# Convenience default used by scripts. The Streamlit app loads settings per-run.
settings = load_settings()
