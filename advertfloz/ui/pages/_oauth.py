"""OAuth start/return helpers shared by the Facebook, Instagram and Connections pages.

The browser is redirected to Meta's official authorization page. The code is exchanged by a
backend callback (the local callback service in local mode, the Cloudflare Worker remotely) —
never by Streamlit. This module only builds the authorize URL, records the one-time state, and
reflects connection state back into the UI.
"""
from __future__ import annotations

from advertfloz.application.services import token_lifecycle
from advertfloz.config import Settings
from advertfloz.domain.enums import ActivationState, AuthFlow, ConnectionState, Platform
from advertfloz.infrastructure.meta import facebook_pages, oauth
from advertfloz.infrastructure.meta.token_store import store_token
from advertfloz.infrastructure.persistence.local_sqlite import Repository
from advertfloz.infrastructure.security.crypto import TokenCipher


def start_oauth(repo: Repository, settings: Settings, platform: Platform) -> tuple[str | None, str]:
    """Return (authorize_url, message). Requires the Meta app to be configured."""
    if not settings.meta_app_configured:
        return None, "Meta Developer App is not configured (META_APP_ID + META_APP_SECRET). Configure it in deployment secrets."
    code_verifier, challenge = oauth.pkce_pair()
    state = oauth.new_state()
    repo.save_oauth_state(state, platform, code_verifier)
    url = oauth.build_authorize_url(
        settings.meta_app_id, settings.meta_oauth_redirect_uri, state, oauth.DEFAULT_SCOPES,
        version=settings.meta_graph_version, code_challenge=challenge,
    )
    return url, "Redirecting to Meta's official authorization page."


def demo_connect(repo: Repository, settings: Settings, platform: Platform, cipher: TokenCipher) -> str:
    """Demo-mode authorization against the mock provider. Never used in configured mode."""
    if settings.mode != "demo":
        raise RuntimeError("demo_connect is only available in demo mode")
    if platform is Platform.FACEBOOK:
        page = facebook_pages.PageRef("demo_page_1", "Demo Page")
        from advertfloz.domain.models import Connection

        repo.upsert_connection(Connection(
            provider=platform, auth_flow=AuthFlow.FACEBOOK_LOGIN, state=ConnectionState.TEST_PASSED,
            account_id=page.page_id, account_name=page.name, page_id=page.page_id, page_name=page.name,
            scopes=oauth.DEFAULT_SCOPES, activation_state=ActivationState.READY_FOR_LOCAL_PILOT,
        ))
        if cipher.configured:
            store_token(repo, cipher, platform, "demo-page-token")
        repo.audit("operator", "connect.demo", platform.value, "demo connection created")
        return "Demo Facebook Page connected. This is demo data, not a live Meta account."
    else:
        from advertfloz.domain.models import Connection

        repo.upsert_connection(Connection(
            provider=platform, auth_flow=AuthFlow.FACEBOOK_LOGIN, state=ConnectionState.TEST_PASSED,
            account_id="demo_ig_1", account_name="demo_ig_user", page_id="demo_page_1", page_name="Demo Page",
            scopes=oauth.DEFAULT_SCOPES, activation_state=ActivationState.READY_FOR_LOCAL_PILOT,
        ))
        if cipher.configured:
            store_token(repo, cipher, platform, "demo-ig-token")
        repo.audit("operator", "connect.demo", platform.value, "demo connection created")
        return "Demo Instagram account connected. This is demo data, not a live Meta account."


def disconnect(repo: Repository, platform: Platform) -> None:

    conn = repo.get_connection(platform)
    if conn is not None:
        conn.state = ConnectionState.DISCONNECTED
        conn.activation_state = ActivationState.NOT_CONFIGURED
        repo.upsert_connection(conn)
    repo.delete_token(platform)
    repo.audit("operator", "disconnect", platform.value, "token removed")


def status_lines(repo: Repository, platform: Platform) -> list[str]:
    conn = repo.get_connection(platform)
    if conn is None:
        return ["Not connected."]
    lines = [
        f"State: {conn.state.value}",
        f"Activation: {conn.activation_state.value}",
        f"Auth flow: {conn.auth_flow.value}",
    ]
    if conn.page_id:
        lines.append(f"Page: {conn.page_name} ({conn.page_id})")
    if conn.account_id:
        lines.append(f"Account: {conn.account_name} ({conn.account_id})")
    if conn.scopes:
        lines.append(f"Scopes: {', '.join(conn.scopes)}")
    health = token_lifecycle.assess_token_health(conn)
    lines.append(health.message)
    return lines
