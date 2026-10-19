# ADR — AdvertFloz v1.7 implementation resolutions

This ADR records the decisions required before OAuth and remote-publishing work. It complements
the supplied `AdvertFloz_Architecture_Decision_Record_v1.7.md`; it does not replace it.

## ADR-1 — OAuth callback topology (local vs remote)

**Decision.** Two explicit, testable callback configurations, one callback owner per mode.

- **Local mode.** `advertfloz/oauth_callback/app.py` (FastAPI) binds to `127.0.0.1:8765`.
  Redirect URI: `http://localhost:8765/oauth/meta/callback`. It validates a single-use `state`
  (plus PKCE verifier stored in SQLite with a TTL), exchanges the code **server-side** with
  `META_APP_SECRET`, writes the encrypted token, and redirects to the control plane. Valid only
  when the operator's browser and the service run on the same machine.
- **Remote mode.** `worker/src/auth/oauth_callback.ts` is the reachable callback
  (`https://<worker-domain>/oauth/meta/callback`). State lives in D1; the code is exchanged
  server-side with the Worker secret; the token is sealed and stored in D1; the browser is
  redirected to the control plane.

**Rationale.** Streamlit Community Cloud is not a suitable OAuth callback backend and a localhost
sidecar is not reachable when hosted. Each mode has exactly one callback owner and one documented
redirect URI.

**Consequences.** Live testing of both topologies requires the real Meta app (Phase 0); the mock
provider exercises the code paths offline.

## ADR-2 — Token exchange, storage, refresh and "transfer"

**Decision.**
- Exchange point = the callback owner only. Tokens never pass through Streamlit session state, the
  browser, Git, logs or untrusted APIs.
- At rest, tokens are AES-256-GCM ciphertext with a `key_id`; the key is a backend secret held
  separately from the database.
- Local consumption: the local scheduler decrypts in-process. Remote: only the Worker decrypts to
  call Meta; the control plane asks the Worker to perform privileged actions and receives
  sanitized results only.
- There is **no token import/export path**. Switching modes requires re-authorization, not copying.
- Rotation: `key_id` is versioned with the ciphertext; a rotation job re-encrypts; revoked keys
  force reconnect. If the key is lost, tokens are unrecoverable and the operator must re-authorize.

**Rationale.** No invented transfer mechanism; the smallest possible set of components ever sees a
token.

## ADR-3 — BYOK and account isolation

**Decision.** Only official Meta OAuth. Pages and eligible linked Instagram professional accounts
are discovered and displayed for selection; no password or raw-token input exists. Two credential
classes are kept separate in schema and code:
(a) deployment-owner secrets (Meta app, Cloudflare/Worker, Telegram, encryption key) — provider
secret manager only; (b) per-account OAuth tokens — encrypted, account-scoped rows keyed to the
connection. Only metadata (provider, IDs/names, flow, scopes, issued/expiry/validated, status) is
readable.

**Rationale.** Prevents credential confusion and cross-account leakage.

## ADR-4 — Zero-cost deployment gate

**Decision.** `scripts/cost_gate.py`, a Worker endpoint and a UI checklist verify Cloudflare
account/Worker eligibility, the R2 payment-method prerequisite, Worker/D1/R2 limits, media
retrieval for the chosen Meta flow, remote auth, backup/restore and external alerts. No automatic
upgrade. If the gate fails, remote mode is **NO-GO** with the reason surfaced in the UI and
`IMPLEMENTATION_STATUS.md`; local mode keeps working; no paid fallback is enabled.

## ADR-5 — Acceptance criteria: mocks vs live

**Decision.** `IMPLEMENTATION_STATUS.md` carries separate "mock evidence" and "live acceptance"
columns. Only an executed live test may set OAuth, publishing, cloud deployment, alerts or the
laptop-off canary to PASS. Compiling code or passing mocks never sets a live row to PASS.

**Consequences.** The deliverable distinguishes "implementation complete" from "live-provider
acceptance pending" in every report.
