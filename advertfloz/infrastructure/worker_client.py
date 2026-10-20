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


def upload_media_to_worker(
    repo: Repository,
    settings: Settings,
    image_id: int,
    filename: str,
    data: bytes,
    mime: str = "image/jpeg",
    sha256: str = "",
) -> str | None:
    """Upload media binary to R2 through worker and update local sync state."""
    import base64
    import json
    from advertfloz.domain.enums import SyncState

    b64_data = base64.b64encode(data).decode("ascii")
    payload = json.dumps({
        "image_id": image_id,
        "filename": filename,
        "mime": mime,
        "sha256": sha256 or hashlib.sha256(data).hexdigest(),
        "data_b64": b64_data,
    })
    res = call_worker(settings, "/api/media/upload", method="POST", body=payload)
    if res and res.get("ok"):
        remote_key = res.get("remote_object_key", f"{image_id}_{filename}")
        repo.update_sync_state(image_id, SyncState.SYNCED, remote_object_key=remote_key)
        return remote_key
    return None


def sync_campaign_to_worker(
    settings: Settings,
    campaign: Any,
    revision: Any,
    posts: list[Any],
    jobs: list[Any],
) -> dict[str, Any] | None:
    """Sync campaign, revision, posts, and jobs to Cloudflare D1 for remote execution."""
    import json

    payload = json.dumps({
        "campaign": {
            "campaign_id": campaign.campaign_id,
            "name": campaign.name,
            "campaign_tag": campaign.campaign_tag,
            "default_timezone": campaign.default_timezone,
            "start_date": campaign.start_date,
            "end_date": campaign.end_date,
            "schema_version": getattr(campaign, "schema_version", "1.7"),
        } if campaign else None,
        "revision": {
            "revision_id": revision.revision_id,
            "campaign_id": revision.campaign_id,
            "manifest_hash": revision.manifest_hash,
            "notes": getattr(revision, "notes", ""),
        } if revision else None,
        "posts": [
            {
                "post_id": p.post_id,
                "campaign_id": p.campaign_id,
                "revision_id": p.revision_id,
                "image_id": p.image_id,
                "scheduled_at": p.scheduled_at,
                "timezone": p.timezone,
                "platforms": getattr(p, "platforms_str", "") or (",".join(p.platforms) if isinstance(getattr(p, "platforms", None), (list, set)) else str(getattr(p, "platforms", "facebook"))),
                "caption": p.caption,
                "facebook_caption": getattr(p, "facebook_caption", ""),
                "instagram_caption": getattr(p, "instagram_caption", ""),
                "alt_text": getattr(p, "alt_text", ""),
                "destination_url": getattr(p, "destination_url", ""),
                "grace_minutes": getattr(p, "grace_minutes", 60),
                "campaign_tag": getattr(p, "campaign_tag", ""),
                "ai_disclosure_status": getattr(p.ai_disclosure_status, "value", str(getattr(p, "ai_disclosure_status", "not_reviewed"))),
                "enabled": getattr(p, "enabled", True),
                "notes": getattr(p, "notes", ""),
            }
            for p in posts
        ],
        "jobs": [
            {
                "job_id": getattr(j, "job_id", 0),
                "campaign_id": j.campaign_id,
                "revision_id": j.revision_id,
                "post_id": j.post_id,
                "platform": getattr(j.platform, "value", str(j.platform)),
                "target_account_id": getattr(j, "target_account_id", ""),
                "status": getattr(j.status, "value", str(j.status)),
                "scheduled_at": j.scheduled_at,
                "timezone": j.timezone,
                "due_at_utc": getattr(j, "due_at_utc", ""),
                "idempotency_key": j.idempotency_key,
                "attempt_count": getattr(j, "attempt_count", 0),
                "next_retry_at": getattr(j, "next_retry_at", ""),
                "remote_post_id": getattr(j, "remote_post_id", ""),
                "permalink": getattr(j, "permalink", ""),
            }
            for j in jobs
        ],
    })
    return call_worker(settings, "/api/campaigns/sync", method="POST", body=payload)

