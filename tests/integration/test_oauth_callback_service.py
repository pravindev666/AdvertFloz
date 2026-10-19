"""Local OAuth callback topology (resolution §1): state validation, single-use, encrypted storage.

Exercises `advertfloz/oauth_callback/app.py` end-to-end against a stubbed Graph client — the code
path the local mode uses in place of Streamlit, which is never the callback backend.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from advertfloz.domain.enums import ConnectionState, Platform  # noqa: E402
from advertfloz.infrastructure.meta.graph_client import GraphResponse  # noqa: E402
from advertfloz.infrastructure.meta.oauth import DEFAULT_SCOPES  # noqa: E402
from advertfloz.infrastructure.meta.token_store import load_token  # noqa: E402
from advertfloz.infrastructure.persistence.local_sqlite import Repository  # noqa: E402
from advertfloz.infrastructure.security.crypto import TokenCipher, generate_key  # noqa: E402

GRANTED_SCOPE = ",".join(DEFAULT_SCOPES)


class FakeGraph:
    """Stubs the token endpoint and Page discovery."""

    def __init__(self, *, page: dict | None = None) -> None:
        self.page = page or {"id": "page-1", "name": "Demo Page", "access_token": "page-token"}

    def post(self, path: str, data: dict, token: str) -> GraphResponse:
        assert path == "token"
        return GraphResponse(200, {"access_token": "USER-TOKEN-SECRET", "token_type": "bearer",
                                   "expires_in": 3600, "scope": GRANTED_SCOPE})

    def get(self, path: str, params: dict, token: str) -> GraphResponse:
        assert path == "me/accounts"
        return GraphResponse(200, {"data": [self.page]})


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "cb.sqlite"
    key = generate_key()
    monkeypatch.setenv("ADVERTFLOZ_DB_PATH", str(db))
    monkeypatch.setenv("ADVERTFLOZ_MODE", "local")
    monkeypatch.setenv("ADVERTFLOZ_CONTROL_PLANE_URL", "http://localhost:8501")
    monkeypatch.setenv("META_APP_ID", "app-1")
    monkeypatch.setenv("META_APP_SECRET", "app-secret")
    monkeypatch.setenv("META_OAUTH_REDIRECT_URI", "http://localhost:8765/oauth/meta/callback")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key)
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY_ID", "k1")

    import advertfloz.oauth_callback.app as app_module

    monkeypatch.setattr(app_module, "HttpGraphClient", lambda version=None: FakeGraph())
    with TestClient(app_module.app) as test_client:
        yield test_client, db, key


def _seed_state(db_path, state: str = "state-abc", verifier: str = "verifier-1") -> None:
    repo = Repository(db_path)
    try:
        repo.save_oauth_state(state, Platform.FACEBOOK, verifier)
    finally:
        repo.close()


def test_callback_exchanges_code_and_stores_encrypted_token(client):
    test_client, db_path, key = client
    _seed_state(db_path)

    response = test_client.get("/oauth/meta/callback", params={"state": "state-abc", "code": "AUTH-CODE"},
                               follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:8501"

    repo = Repository(db_path)
    try:
        conn = repo.get_connection(Platform.FACEBOOK)
        assert conn is not None
        assert conn.state is ConnectionState.TARGET_SELECTED
        assert conn.page_id == "page-1"
        # Token is present, encrypted, and decryptable with the separate key.
        assert load_token(repo, TokenCipher.single(key, "k1"), Platform.FACEBOOK) == "USER-TOKEN-SECRET"
        raw = db_path.read_bytes()
        assert b"USER-TOKEN-SECRET" not in raw
    finally:
        repo.close()


def test_state_is_single_use(client):
    test_client, db_path, _ = client
    _seed_state(db_path, state="once")
    first = test_client.get("/oauth/meta/callback", params={"state": "once", "code": "c"}, follow_redirects=False)
    assert first.status_code == 303
    replay = test_client.get("/oauth/meta/callback", params={"state": "once", "code": "c"}, follow_redirects=False)
    assert replay.status_code == 400
    assert "invalid" in replay.text.lower() or "used" in replay.text.lower()


def test_unknown_state_rejected(client):
    test_client, _, _ = client
    response = test_client.get("/oauth/meta/callback", params={"state": "never-issued", "code": "c"},
                               follow_redirects=False)
    assert response.status_code == 400


def test_provider_error_is_reported(client):
    test_client, _, _ = client
    response = test_client.get("/oauth/meta/callback", params={"error": "access_denied",
                                                              "error_description": "user cancelled"},
                               follow_redirects=False)
    assert response.status_code == 400
    assert "access_denied" in response.text


def test_missing_state_rejected(client):
    test_client, _, _ = client
    response = test_client.get("/oauth/meta/callback", params={"code": "c"}, follow_redirects=False)
    assert response.status_code == 400


def test_health_endpoint(client):
    test_client, _, _ = client
    assert test_client.get("/health").json()["status"] == "ok"
