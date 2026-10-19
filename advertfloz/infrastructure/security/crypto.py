"""Application-layer token encryption using AES-256-GCM.

Established AEAD only — no home-grown crypto. The key is supplied from a backend secret
and is never stored in the database, backups, logs or exports. Ciphertext rows carry a
``key_id`` so keys can be rotated without guessing which key encrypted a value.
"""
from __future__ import annotations

import base64
import os
import secrets
import sys
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12
KEY_BYTES = 32


class CryptoError(RuntimeError):
    """Raised when a token cannot be encrypted or decrypted safely."""


def generate_key() -> str:
    """Return a fresh urlsafe-base64 32-byte key suitable for TOKEN_ENCRYPTION_KEY."""
    return base64.urlsafe_b64encode(secrets.token_bytes(KEY_BYTES)).decode("ascii")


def _decode_key(value: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(value.encode("ascii"))
    except Exception as exc:  # pragma: no cover - defensive
        raise CryptoError("TOKEN_ENCRYPTION_KEY is not valid urlsafe base64") from exc
    if len(raw) != KEY_BYTES:
        raise CryptoError(f"TOKEN_ENCRYPTION_KEY must decode to {KEY_BYTES} bytes")
    return raw


@dataclass
class TokenCipher:
    keys: dict[str, bytes] = field(default_factory=dict)
    primary_id: str = "k1"

    @classmethod
    def from_mapping(cls, mapping: dict[str, str], primary_id: str = "k1") -> TokenCipher:
        keys = {kid: _decode_key(val) for kid, val in mapping.items() if val}
        return cls(keys=keys, primary_id=primary_id)

    @classmethod
    def single(cls, key_value: str, key_id: str = "k1") -> TokenCipher:
        if not key_value:
            raise CryptoError("no encryption key configured")
        return cls(keys={key_id: _decode_key(key_value)}, primary_id=key_id)

    @property
    def configured(self) -> bool:
        return bool(self.keys)

    def encrypt(self, plaintext: str) -> tuple[str, bytes, bytes]:
        """Return (key_id, nonce, ciphertext)."""
        if not self.configured:
            raise CryptoError("no encryption key configured; cannot store tokens")
        key = self.keys[self.primary_id]
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
        return self.primary_id, nonce, ciphertext

    def decrypt(self, key_id: str, nonce: bytes, ciphertext: bytes) -> str:
        key = self.keys.get(key_id)
        if key is None:
            raise CryptoError(f"missing encryption key {key_id!r}; restore it from the secret manager")
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")
        except InvalidTag as exc:
            raise CryptoError("token ciphertext failed authentication") from exc


def _main(argv: list[str]) -> int:
    if argv and argv[0] == "genkey":
        sys.stdout.write(generate_key() + "\n")
        return 0
    sys.stderr.write("usage: python -m advertfloz.infrastructure.security.crypto genkey\n")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main(sys.argv[1:]))
