"""Encrypt/decrypt OAuth tokens at the boundary of the persistence layer.

Tokens are only ever plaintext in memory inside the component that calls the provider (the
local scheduler or the remote Worker). They are never written to logs, exports or the UI.
"""
from __future__ import annotations

from ...domain.enums import Platform, SyncState  # noqa: F401  (re-exported context)
from ..persistence.local_sqlite import Repository
from ..security.crypto import CryptoError, TokenCipher


def store_token(repo: Repository, cipher: TokenCipher, platform: Platform, token_plaintext: str) -> str:
    key_id, nonce, ciphertext = cipher.encrypt(token_plaintext)
    repo.store_token(platform, key_id, nonce, ciphertext)
    return key_id


def load_token(repo: Repository, cipher: TokenCipher, platform: Platform) -> str | None:
    blob = repo.get_token_blob(platform)
    if blob is None:
        return None
    key_id, nonce, ciphertext = blob
    try:
        return cipher.decrypt(key_id, nonce, ciphertext)
    except CryptoError:
        return None


def drop_token(repo: Repository, platform: Platform) -> None:
    repo.delete_token(platform)
