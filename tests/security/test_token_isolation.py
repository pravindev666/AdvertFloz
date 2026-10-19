"""Security tests: tokens never appear in plaintext in the database or the UI layer."""
from __future__ import annotations

from pathlib import Path

from advertfloz.domain.enums import Platform
from advertfloz.infrastructure.meta.token_store import load_token, store_token
from advertfloz.infrastructure.security.crypto import TokenCipher, generate_key
from tests.builders import seed_connection


def _cipher() -> TokenCipher:
    return TokenCipher.single(generate_key(), "k1")


def test_tokens_are_encrypted_at_rest(repo, tmp_path: Path):
    seed_connection(repo, Platform.FACEBOOK)
    seed_connection(repo, Platform.INSTAGRAM)
    cipher = _cipher()
    store_token(repo, cipher, Platform.FACEBOOK, "FB-SECRET-VALUE-123")
    store_token(repo, cipher, Platform.INSTAGRAM, "IG-SECRET-VALUE-456")

    raw = Path(repo.db_path).read_bytes()
    assert b"FB-SECRET-VALUE-123" not in raw
    assert b"IG-SECRET-VALUE-456" not in raw

    assert load_token(repo, cipher, Platform.FACEBOOK) == "FB-SECRET-VALUE-123"
    assert load_token(repo, cipher, Platform.INSTAGRAM) == "IG-SECRET-VALUE-456"


def test_connections_have_no_token_field(repo):
    seed_connection(repo, Platform.FACEBOOK)
    conn = repo.get_connection(Platform.FACEBOOK)
    assert conn is not None
    # The readable connection object carries only metadata — never a token.
    assert not hasattr(conn, "access_token")
    assert not hasattr(conn, "token")


def test_per_provider_tokens_are_isolated(repo):
    seed_connection(repo, Platform.FACEBOOK)
    seed_connection(repo, Platform.INSTAGRAM)
    cipher = _cipher()
    store_token(repo, cipher, Platform.FACEBOOK, "FB")

    # Instagram has no token until it is explicitly connected.
    assert load_token(repo, cipher, Platform.INSTAGRAM) is None
    assert load_token(repo, cipher, Platform.FACEBOOK) == "FB"
    assert repo.get_token_blob(Platform.INSTAGRAM) is None


def test_missing_key_cannot_decrypt(repo):
    seed_connection(repo, Platform.FACEBOOK)
    store_token(repo, _cipher(), Platform.FACEBOOK, "secret")
    other = TokenCipher.single(generate_key(), "k1")
    assert load_token(repo, other, Platform.FACEBOOK) is None


def test_oauth_states_are_single_use(repo):
    repo.save_oauth_state("state-1", Platform.FACEBOOK, "verifier-1")
    assert repo.consume_oauth_state_any("state-1") == (Platform.FACEBOOK, "verifier-1")
    assert repo.consume_oauth_state_any("state-1") is None
