# Threat model — AdvertFloz v1.7

Scope: a single-operator tool. Local mode runs on one laptop; remote mode is one private,
authenticated control plane plus a Cloudflare Worker. Multi-tenant public hosting is out of scope.

## Assets

- Meta OAuth access tokens (per account) and the token-encryption key.
- Deployment-owner secrets: Meta App Secret, Cloudflare/Worker service key, Telegram bot token.
- Campaign data: captions, destinations, schedules, media, audit history.
- The operator's provider accounts (publishing rights).

## Trust boundaries

- Browser ↔ control plane (Streamlit).
- Control plane ↔ local scheduler (same machine, shared SQLite).
- Control plane ↔ Cloudflare Worker (authenticated service-to-service).
- Callback owner ↔ Meta (server-side code exchange).
- Worker ↔ D1 / R2.

## Threats and mitigations

| Threat | Mitigation |
|---|---|
| Token theft from storage | AES-256-GCM at rest with a `key_id`; key held outside the DB as a backend secret; ciphertext-only backups; no token in logs/UI/exports |
| Token leakage via logs/errors | `redaction.py` masks Authorization headers, `code`, `access_token`, bot tokens and Meta token prefixes; `GraphResponse.sanitized_summary()` used for all provider errors |
| Replayed OAuth callback | Single-use `state` + PKCE verifier with TTL; consumed exactly once (local: SQLite; remote: D1) |
| Callback URI mismatch | Exact redirect URI configured per mode and recorded in `PROVIDER_COMPATIBILITY.md` |
| Malicious upload (Zip Slip, symlinks, nested archives, zip bombs) | `zip_validation.py`: flat-only, path traversal/symlink/metadata rejection, magic-byte + decoder checks, per-asset and expanded-byte caps, compression-ratio check; extraction only into a per-import sandbox |
| Uploaded content executed | Nothing from an upload is ever executed; Markdown/text is rendered as data only |
| Blind retry creating duplicates | Idempotency key per `campaign_id:revision:post_id:platform`; leases prevent concurrent claims; `UNKNOWN_OUTCOME` blocks retry until reconciliation |
| Unauthorized remote control | Bearer service key + HMAC signature over method/path/timestamp/nonce/body; timestamp window; single-use nonce (replay rejection); rotation via a second accepted key |
| Anonymous hosted control panel | `enforce_hosted_gate()` fails closed without an IdP and operator allowlist; loopback-only no-login |
| Unauthorized Telegram commands | Allow-listed chat id; webhook secret verification; rate limiting; every command audited |
| Sensitive data in URLs | UTM generation restricted to stable non-personal fields (`build_utm` rejects unsafe tokens) |
| Cost shock | Zero-cost gate, no auto-upgrade, hard stops, spend warnings |
| Media over-exposure | R2 stays private; short-lived HMAC-signed URLs only |

## Residual risks (documented, not hidden)

- If the token-encryption key is stored beside the ciphertext with no OS protection, the at-rest
  threat model is weaker and is not claimed as strong.
- Exactly-once external delivery cannot be guaranteed; ambiguous outcomes are reconciled honestly.
- Free-tier provider limits and eligibility are not guaranteed and are verified per account.
