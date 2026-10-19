"""Local-mode Meta OAuth callback service.

Run on loopback only:

    uvicorn advertfloz.oauth_callback.app:app --host 127.0.0.1 --port 8765

This is the *only* component that sees the authorization code, exchanges it server-side and
writes the encrypted token. Streamlit never handles the code or the token. Hosted/remote mode
uses the Cloudflare Worker callback instead — a localhost service must not be assumed reachable
when hosted.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from html import escape

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..config import load_settings
from ..domain.enums import ActivationState, AuthFlow, ConnectionState, Platform
from ..domain.models import Connection
from ..infrastructure.meta import facebook_pages, instagram_publish, oauth
from ..infrastructure.meta.graph_client import HttpGraphClient
from ..infrastructure.meta.token_store import store_token
from ..infrastructure.persistence.local_sqlite import Repository
from ..infrastructure.security.crypto import TokenCipher
from ..infrastructure.security.redaction import install_redacting_logging

install_redacting_logging(logging.INFO)
logger = logging.getLogger("advertfloz.oauth_callback")

app = FastAPI(title="AdvertFloz OAuth callback", docs_url=None, redoc_url=None)


def _cipher(settings) -> TokenCipher:
    key = settings.secret("TOKEN_ENCRYPTION_KEY")
    if not key:
        return TokenCipher()
    return TokenCipher.single(key, settings.token_encryption_key_id)


def _error_page(message: str, status_code: int = 400) -> HTMLResponse:
    return HTMLResponse(
        f"<h3>AdvertFloz authorization failed</h3><p>{escape(message)}</p>",
        status_code=status_code,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "advertfloz-oauth-callback"}


@app.get("/oauth/meta/callback")
def callback(request: Request, code: str | None = None, state: str | None = None,
             error: str | None = None, error_description: str | None = None):
    """Handle Meta's redirect: validate one-time state, exchange the code server-side."""
    settings = load_settings()
    repo = Repository(settings.db_path)
    try:
        if error:
            repo.audit("meta", "oauth.denied", "", f"provider error: {error}")
            return _error_page(f"Meta returned an error: {error} {error_description or ''}")

        if not state:
            return _error_page("Missing OAuth state.")
        consumed = repo.consume_oauth_state_any(state)
        if consumed is None:
            repo.audit("meta", "oauth.state_rejected", "", "expired, unknown or replayed state")
            return _error_page("OAuth state is invalid, expired, or already used. Restart the connection.")
        platform, code_verifier = consumed

        if not code:
            return _error_page("Missing authorization code.")

        if not settings.meta_app_configured:
            return _error_page("Meta app is not configured on this installation.")

        client = HttpGraphClient(version=settings.meta_graph_version)
        token, resp = oauth.exchange_code(
            client, settings.meta_app_id, settings.secret("META_APP_SECRET"),
            settings.meta_oauth_redirect_uri, code, code_verifier or None,
        )
        if token is None:
            repo.audit("meta", "oauth.exchange_failed", platform.value, resp.sanitized_summary())
            return _error_page("The authorization code could not be exchanged. Check the callback URI and app secret.")

        missing = oauth.validate_granted_scopes(token)
        if oauth.missing_scope_is_blocking(missing):
            repo.audit("meta", "oauth.scope_missing", platform.value, ",".join(missing))
            return _error_page(f"Required permissions were not granted: {', '.join(missing)}")

        cipher = _cipher(settings)
        if not cipher.configured:
            return _error_page("TOKEN_ENCRYPTION_KEY is not configured; refusing to store a token in plaintext.")

        expires_at = ""
        if token.expires_in:
            expires_at = (datetime.now(UTC) + timedelta(seconds=token.expires_in)).isoformat(timespec="seconds")

        conn_state = ConnectionState.CONNECTED_NO_TARGET
        account_id = account_name = page_id = page_name = ""
        if platform is Platform.FACEBOOK:
            pages = facebook_pages.list_pages(client, token.access_token)
            if pages.ok and pages.pages:
                first = pages.pages[0]
                page_id, page_name = first.page_id, first.name
                conn_state = ConnectionState.TARGET_SELECTED
        else:
            conn = repo.get_connection(Platform.FACEBOOK)
            if conn is not None and conn.page_id:
                discovery = instagram_publish.discover_account(client, conn.page_id, token.access_token)
                if discovery.ok and discovery.account:
                    account_id, account_name = discovery.account.ig_user_id, discovery.account.username
                    conn_state = ConnectionState.TARGET_SELECTED

        repo.upsert_connection(Connection(
            provider=platform, auth_flow=AuthFlow.FACEBOOK_LOGIN, state=conn_state,
            account_id=account_id, account_name=account_name, page_id=page_id, page_name=page_name,
            scopes=token.scopes, issued_at=datetime.now(UTC).isoformat(timespec="seconds"),
            expires_at=expires_at, last_validated_at=datetime.now(UTC).isoformat(timespec="seconds"),
            activation_state=ActivationState.READY_FOR_LOCAL_PILOT if conn_state is ConnectionState.TARGET_SELECTED
            else ActivationState.NEEDS_OPERATOR_ACTION,
        ))
        store_token(repo, cipher, platform, token.access_token)
        repo.audit("meta", "oauth.connected", platform.value, f"state={conn_state.value}")

        return RedirectResponse(settings.control_plane_url, status_code=303)
    finally:
        repo.close()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (
        "<h3>AdvertFloz OAuth callback service</h3>"
        "<p>Loopback-only callback for Meta authorization. Configure this exact URI in the Meta app: "
        "<code>/oauth/meta/callback</code>.</p>"
    )
