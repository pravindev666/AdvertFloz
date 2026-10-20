"""Worker API client and remote connection synchronizer."""
from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from typing import Any
import requests

from advertfloz.config import Settings
from advertfloz.domain.enums import ActivationState, AuthFlow, ConnectionState, Platform
from advertfloz.domain.models import Connection
from advertfloz.infrastructure.persistence.local_sqlite import Repository


def call_worker(settings: Settings, path: str, method: str = "GET", body: str = "") -> dict[str, Any] | None:
    """Call Cloudflare Worker authenticated with HMAC service key."""
    if not settings.worker_configured:
        return None
    base_url = settings.worker_base_url.rstrip("/")
    url = f"{base_url}{path}"
    path_only = path.split("?")[0]
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    message = f"{method}\n{path_only}\n{timestamp}\n{nonce}\n{body}".encode("utf-8")
    sig = hmac.new(settings.worker_service_key.encode("utf-8"), message, hashlib.sha256).hexdigest()

    headers = {
        "Authorization": f"Bearer {settings.worker_service_key}",
        "x-advertfloz-timestamp": timestamp,
        "x-advertfloz-nonce": nonce,
        "x-advertfloz-signature": sig,
    }
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=15)
        else:
            headers["Content-Type"] = "application/json"
            resp = requests.post(url, data=body, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        return None
    return None


def sync_remote_connections(repo: Repository, settings: Settings) -> list[Connection]:
    """Sync connections from Cloudflare D1 into local SQLite repository."""
    if not settings.worker_configured:
        return []

    data = call_worker(settings, "/api/connections")
    if not data or "connections" not in data:
        return []

    synced: list[Connection] = []
    for row in data["connections"]:
        provider_str = str(row.get("provider", ""))
        if provider_str not in {"facebook", "instagram"}:
            continue
        provider = Platform(provider_str)

        state_str = str(row.get("state", "not_connected"))
        try:
            state = ConnectionState(state_str)
        except ValueError:
            state = ConnectionState.CONNECTED_NO_TARGET

        try:
            activation = ActivationState(str(row.get("activation_state", "Not configured")))
        except ValueError:
            activation = ActivationState.NEEDS_OPERATOR_ACTION

        try:
            auth_flow = AuthFlow(str(row.get("auth_flow", "facebook_login")))
        except ValueError:
            auth_flow = AuthFlow.FACEBOOK_LOGIN

        raw_scopes = row.get("scopes") or ""
        scopes = [s.strip() for s in raw_scopes.split(",") if s.strip()] if isinstance(raw_scopes, str) else []

        conn = Connection(
            provider=provider,
            auth_flow=auth_flow,
            state=state,
            account_id=str(row.get("account_id") or ""),
            account_name=str(row.get("account_name") or ""),
            page_id=str(row.get("page_id") or ""),
            page_name=str(row.get("page_name") or ""),
            scopes=scopes,
            activation_state=activation,
        )
        repo.upsert_connection(conn)
        synced.append(conn)

    return synced


def sync_meta_pages(repo: Repository, settings: Settings, page_id: str | None = None) -> dict[str, Any] | None:
    """Ask worker to fetch Facebook pages from Meta Graph API using stored token."""
    if not settings.worker_configured:
        return None

    path = "/api/meta/pages"
    if page_id:
        path += f"?page_id={page_id}"

    data = call_worker(settings, path, method="GET")
    if data and "selected_page" in data:
        sync_remote_connections(repo, settings)
    return data
