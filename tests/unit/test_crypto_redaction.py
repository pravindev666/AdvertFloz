"""Unit tests for AEAD token encryption and log redaction (FR-014, NFR-13)."""
from __future__ import annotations

import pytest

from advertfloz.infrastructure.security.crypto import CryptoError, TokenCipher, generate_key
from advertfloz.infrastructure.security.redaction import redact


def test_roundtrip_and_key_id():
    cipher = TokenCipher.single(generate_key(), "k1")
    key_id, nonce, ciphertext = cipher.encrypt("secret-token")
    assert key_id == "k1"
    assert b"secret-token" not in ciphertext
    assert cipher.decrypt(key_id, nonce, ciphertext) == "secret-token"


def test_wrong_key_fails_authentication():
    a = TokenCipher.single(generate_key(), "k1")
    b = TokenCipher.single(generate_key(), "k1")
    key_id, nonce, ciphertext = a.encrypt("secret")
    with pytest.raises(CryptoError):
        b.decrypt(key_id, nonce, ciphertext)


def test_missing_key_is_explicit():
    with pytest.raises(CryptoError):
        TokenCipher.single("")


def test_rotation_keeps_old_key_readable():
    old = generate_key()
    new = generate_key()
    writer = TokenCipher.from_mapping({"k1": old}, "k1")
    key_id, nonce, ciphertext = writer.encrypt("token")
    reader = TokenCipher.from_mapping({"k1": old, "k2": new}, "k2")
    assert reader.decrypt(key_id, nonce, ciphertext) == "token"


def test_redaction_masks_credentials():
    text = "Authorization: Bearer EAAabcdefghijklmnopqrstuvwxyz123 code=AQD123 access_token=xyz 123456:ABCdef-tokenvalue"
    out = redact(text)
    assert "EAAabcdefghijklmnopqrstuvwxyz123" not in out
    assert "access_token=xyz" not in out
    assert "123456:ABCdef-tokenvalue" not in out
    assert out.count("***REDACTED***") >= 3
