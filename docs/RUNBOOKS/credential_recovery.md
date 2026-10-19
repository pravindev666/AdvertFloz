# Runbook — credential recovery and rotation

Never share secret values in chat, tickets or screenshots. This runbook lists secret **names** and
**locations** only.

## Secrets the operator must configure

| Secret | Where it belongs | Notes |
|---|---|---|
| `META_APP_ID` | deployment secret / `.env` | Not secret on its own; may be shown |
| `META_APP_SECRET` | deployment secret / `.env` / Streamlit secrets | Never displayed, logged or committed |
| `META_OAUTH_REDIRECT_URI` | deployment config | Must match the Meta app exactly |
| `TOKEN_ENCRYPTION_KEY` | backend secret (env / Streamlit secrets / OS keyring / Worker secret) | 32-byte urlsafe base64; keep OUTSIDE the database |
| `TOKEN_ENCRYPTION_KEY_ID` | deployment config | Version tag stored with each ciphertext |
| `TELEGRAM_BOT_TOKEN` | backend secret | Optional |
| `TELEGRAM_ALLOWED_CHAT_ID` | deployment config | Identifier, not a credential |
| `TELEGRAM_WEBHOOK_SECRET` | backend secret | Enables webhook verification |
| `WORKER_BASE_URL`, `WORKER_SERVICE_KEY` | deployment secret | Remote plane only |
| `ADVERTFLOZ_MEDIA_BASE_URL` | deployment config | Public HTTPS base Meta can fetch media from |

Generate a key: `python -m advertfloz.infrastructure.security.crypto genkey`

## Lost the encryption key

Tokens are unrecoverable. Restore the key from your password/secret manager. If it is genuinely
gone, reconnect each platform (re-authorize) — do not attempt to fabricate tokens.

## Rotating the encryption key

1. Add the new key under a new `key_id` and keep the old key available.
2. Re-encrypt stored tokens (decrypt with the old `key_id`, encrypt with the new) — the repository
   stores `key_id` per row so both can coexist during rotation.
3. Remove the old key once no ciphertext references it.

## Rotating the Worker service key

1. Set `WORKER_SERVICE_KEY_PREVIOUS` to the current key and set the new `WORKER_SERVICE_KEY`.
2. Update the control plane to the new key.
3. Remove the previous key after the rotation window.

## Revoking a compromised credential

- Meta: revoke the app/account access in Meta security settings, then reconnect in AdvertFloz.
- Cloudflare: roll the API token / service key in the dashboard, then update deployment secrets.
- Telegram: revoke the bot token with BotFather, then reconfigure.
