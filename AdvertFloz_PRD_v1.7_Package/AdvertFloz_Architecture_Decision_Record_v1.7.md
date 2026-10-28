# AdvertFloz Architecture Decision Record v1.7

## 1. Streamlit is the control plane, not scheduler of record

Chosen: Streamlit + Python handle prompt building, CSV/ZIP validation, calendar, manual image-production tracking, and controls. Local mode uses SQLite and local execution for the Facebook thin slice. Remote mode uses a separate scheduler and durable state/media store.

Reason: Streamlit sessions/apps can restart or hibernate. A 365-day schedule cannot exist only in a browser session or on a sleeping laptop.

## 2. Cloudflare preferred, but subject to Phase 0

Preferred after feasibility checks: Cloudflare Worker Cron for bounded scheduling, D1 for durable state, private R2 for media, optional Telegram and independent uptime monitoring. Each invocation processes a small set of jobs. Instagram create-container/process/publish is a persisted state machine resumed across Cron ticks; do not sleep in one invocation.

GitHub Actions role: lint, tests, campaign validator, build/deploy and release artifacts. It is not the default social publishing scheduler. It may become a fallback scheduler only after a separate proof of concept demonstrates external durable DB/media, serializable state, pause controls, alerts, safe retry and restore. Never store live campaign state or OAuth tokens in Git commits.

Phase 0 must verify actual R2 checkout/payment prerequisites, free quotas, Worker limits, media access and restore. If strict no-payment-details/no-spend constraints are not met, test a fallback or declare remote mode no-go.

## 3. Credential ownership and BYOK

- End users own social accounts and authorize them through Meta OAuth.
- The installation/deployment owner owns the Meta Developer App ID/Secret and infrastructure keys. Self-hosters can bring their own app credentials in deployment secrets.
- Normal users never paste FB/IG passwords, raw OAuth tokens, Meta App Secret or Cloudflare API tokens into normal dashboard fields.
- OAuth tokens are acquired and exchanged server-side, and encrypted at rest remotely; encryption key is separate from stored ciphertext.
- Telegram Bot Token is optional installation-level secret; chat ID is allow-listed.
- AI provider keys are not needed because the user manually uses an external LLM.

## 4. Meta connection flow

Initial preferred route: Facebook Login with an eligible Facebook Page and its linked Instagram professional account. OAuth discovers actual Page names/IDs and linked IG details; operator selects targets from returned data and confirms via test post. Direct Instagram Login is a separate adapter with distinct scopes and requirements and is added only after a Phase 0 account test.

Any connection path must validate OAuth state/callback, exchange codes server-side, validate scopes, store tokens securely, preserve token metadata, support disconnect/reconnect, and avoid token values in UI/logs. A Page name/ID is metadata, not a credential.

## 5. Exact external LLM contract

The external LLM generates two human-readable 365-day Markdown libraries plus `campaign_plan.csv`, `image_prompts.csv`, `campaign_manifest.json`, a continuity ledger, validation and assumptions. It does not generate actual image files. The human generates each image, exports true JPEG bytes and names assets `1.jpg` through `365.jpg`. AdvertFloz imports CSV plus image ZIPs and maps only by image ID, never ZIP order.

## 6. Strict v1.7 media scope

Only static single-image feed posts can be automatically published. Carousels, Stories, Reels and video require more than one image or another media lifecycle and cannot be passed off as one JPG. They remain non-publishable recommendations until separately implemented.

## 7. Security modes

Local no-login mode is allowed only on loopback. Hosted controls must be private/authenticated. Shared-hosted multi-user use requires tenant identity and tenant-scoped token/data isolation; it is not anonymous in v1.7.

## 8. Retry rules

Use durable lease/idempotency key. Definitive transient failures may back off; permanent permission/account restriction failures pause the channel; any response where Meta may have accepted the post is `UNKNOWN_OUTCOME` and must be reconciled before retry. Facebook/Instagram statuses remain independent.
