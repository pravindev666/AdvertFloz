# AdvertFloz Connections, BYOK and Credential Runbook v1.7

## Basic rule

Users connect their own Facebook Page and Instagram professional account using Meta's official authorization flow. They do **not** paste their Facebook/Instagram passwords into AdvertFloz. AdvertFloz discovers eligible Page/account names and IDs after authorization and lets the operator select the target.

## BYOK ownership table

| Item | Owner | How supplied | Storage |
|---|---|---|---|
| Facebook/Instagram account | Operator/user | Official Meta OAuth | Provider-issued token managed server-side; encrypted at rest remotely |
| Page name/ID, IG username/ID | Provider metadata | Discovered after OAuth; user selects target | Store IDs/names as target metadata |
| Facebook/Instagram password | User/Meta | Never entered in AdvertFloz | Never stored |
| Meta App ID/Secret | Installation/deployment owner | Deployment secret settings; self-hosters can bring own Meta App | Secret manager only; App Secret never displayed, logged or committed |
| Cloudflare/GitHub deploy token | Infrastructure owner | CLI/dashboard/GitHub Actions secrets | Deployment secret store only |
| OAuth access/refresh token | Issued for user's account | Backend exchanges authorization code | Encrypt remote token ciphertext; key stored separately |
| Telegram Bot Token | Installation operator | Backend/deployment secret | Never re-display |
| Telegram chat ID | Alert recipient | Verify/allow-list during setup | Store exact allow-listed ID |
| AI API key | Not needed | No field | Campaign is generated manually in external AI conversation |

## Facebook Page flow

1. Deployment owner configures Meta App ID/Secret and the exact allowed callback URI.
2. Go to **Connections & Credentials → Facebook Page → Connect Facebook**.
3. Browser redirects to Meta. User signs in directly on Meta and reviews permissions.
4. Backend verifies a one-time OAuth `state`, exchanges the code server-side, validates scopes and queries authorized Pages.
5. UI lists real Page names and IDs; operator selects one and confirms.
6. Run a non-publishing permission test, followed by an explicitly confirmed test post.
7. Store Page ID, token metadata and result ID/permalink. Never return token plaintext to the UI.

## Instagram flow

1. Open **Instagram → Connect Instagram**.
2. UI declares which login flow is configured. Initial supported path should prefer an eligible professional Instagram account linked to the selected Facebook Page, using the tested Instagram API with Facebook Login flow.
3. Backend discovers the linked professional account; user confirms returned username/ID and runs a separate publishing test.
4. If no eligible account is found, block Instagram activation and show the account-linking instructions. Do not request a password/token.
5. Direct Instagram Login is a separately configured path with its own current scopes; only enable it after implementation and Phase 0 tests.

## Deployment-level Meta App setup

For a self-hosted/BYO Meta App installation:
- Register/configure the Meta Developer app for the intended API flow.
- Configure the actual OAuth redirect URI in the Meta app and ensure it matches the running callback exactly.
- Check current permission names, app mode, test roles and review requirements.
- Supply `META_APP_ID`, `META_APP_SECRET`, `META_OAUTH_REDIRECT_URI` and the token-encryption key through a local ignored secret file or remote secret manager.
- Never place real values in Streamlit text inputs, CSV/Markdown, ZIPs, logs, screenshots, Git, `.env.example`, or backups.

## Local and remote secrets

- **Local:** keep `.env`/`.streamlit/secrets.toml` out of Git. Prefer OS keyring or encrypted store for tokens. Secure the laptop OS account and backup media.
- **Remote:** set app/deploy credentials in the provider secret manager. Encrypt per-user OAuth tokens at application layer before durable DB storage. Keep encryption key separate, e.g. as a Worker secret. D1 must not store raw tokens.
- Do not log Authorization headers, OAuth callback queries, authorization code, token responses, bot tokens or secrets. Show connection state, expiry and granted-scope summary only.
- Secret-free backup restore requires the operator to restore deployment secrets and the encryption key from the password manager/secret manager before reconnecting token records.

## Token lifecycle

Store flow, token type, scopes, issue time, known expiry and last successful validation. Alert 14 days before a known expiry. Refresh only through the selected flow's supported mechanism. If expired/revoked or refresh unsupported, pause that platform and request reauthorization. Re-test permissions and target selection after reconnecting.

## Hosted access

An internet-accessible no-login Streamlit app with controls that can publish or alter credentials is not acceptable. Hosted control plane must be private/authenticated. v1.7 is single-operator per installation; sharing one instance among multiple independent users requires separate app auth, tenant isolation and per-tenant encrypted credential storage before release.
