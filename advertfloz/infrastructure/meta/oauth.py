"""Meta OAuth flow primitives (official authorization code flow + PKCE).

Shared by the local callback service and mirrored in the Cloudflare Worker. The
authorization code is always exchanged server-side; the token never reaches the browser,
Streamlit session state, logs or exports.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from urllib.parse import urlencode

from .graph_client import GraphClient, GraphResponse

AUTHORIZE_URL = "https://www.facebook.com/{version}/dialog/oauth"
TOKEN_URL = "token"

#: Permission names for the Instagram API with Facebook Login path. Verify current names
#: from official Meta docs during Phase 0 (recorded in docs/PROVIDER_COMPATIBILITY.md).
DEFAULT_SCOPES = (
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "instagram_basic",
    "instagram_content_publish",
    "business_management",
)


@dataclass
class TokenResponse:
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 0
    scopes: tuple[str, ...] = ()
    raw: dict = field(default_factory=dict)


def new_state() -> str:
    return secrets.token_urlsafe(24)


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def build_authorize_url(
    app_id: str,
    redirect_uri: str,
    state: str,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
    version: str = "v21.0",
    code_challenge: str | None = None,
) -> str:
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
        "scope": ",".join(scopes),
    }
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    return f"{AUTHORIZE_URL.format(version=version)}?{urlencode(params)}"


def exchange_code(
    client: GraphClient,
    app_id: str,
    app_secret: str,
    redirect_uri: str,
    code: str,
    code_verifier: str | None = None,
) -> tuple[TokenResponse | None, GraphResponse]:
    data: dict = {
        "client_id": app_id,
        "client_secret": app_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if code_verifier:
        data["code_verifier"] = code_verifier
    resp = client.post(TOKEN_URL, data, token="")
    if not resp.ok or "access_token" not in resp.json:
        return None, resp
    scopes = tuple(s for s in (resp.json.get("scope", "") or "").split(",") if s)
    token = TokenResponse(
        access_token=resp.json["access_token"],
        token_type=resp.json.get("token_type", "bearer"),
        expires_in=int(resp.json.get("expires_in", 0) or 0),
        scopes=scopes,
        raw={k: v for k, v in resp.json.items() if k not in {"access_token"}},
    )
    return token, resp


def validate_granted_scopes(token: TokenResponse, required: tuple[str, ...] = DEFAULT_SCOPES) -> list[str]:
    """Return the required scopes that were NOT granted."""
    return [scope for scope in required if scope not in token.scopes]


def missing_scope_is_blocking(missing: list[str]) -> bool:
    """Any missing publish-critical scope blocks publishing for that platform."""
    critical = {"pages_show_list", "pages_manage_posts", "instagram_content_publish"}
    return any(scope in critical for scope in missing)
