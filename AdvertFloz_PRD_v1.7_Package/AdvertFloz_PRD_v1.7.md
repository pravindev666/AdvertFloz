# AdvertFloz — Product Requirements Document

**Version:** 1.7 — account connection, BYOK and deterministic campaign package  
**Date:** 18 October 2026  
**Status:** Implementation specification; not a deployed product  
**UI:** Streamlit + Python  
**Remote plane (preferred, subject to Phase 0):** Cloudflare Worker Cron + D1 + private R2 or a verified no-cost substitute  
**Code/release pipeline:** GitHub + GitHub Actions  
**Budget target:** ₹0 recurring infrastructure/software spend; no automatic paid upgrades

---

## 0. Purpose and core decision

AdvertFloz is a campaign importer, manual-image-production tracker, calendar/review interface, and Facebook/Instagram publisher. The user does **not** upload a product repository to AdvertFloz. Instead, the user downloads a customized master prompt from AdvertFloz, uploads the RASHINOS/MusikFlo/other repository directly to ChatGPT or another chosen LLM, and asks that LLM to produce a precisely defined campaign package. The user manually generates each actual image from the image-prompt library, names the file according to `image_id`, and uploads the campaign CSV and ZIP asset parts to AdvertFloz.

This release resolves five linked questions:

1. How do users connect their own Facebook Page and Instagram account safely?
2. What does BYOK mean, and which keys belong to the user versus the app/deployment operator?
3. What exact Markdown, CSV, manifest and ZIP structure must the external LLM produce?
4. How does the app verify that each caption/date/platform points to the right image before publishing?
5. How can publishing continue when the laptop or Streamlit UI is off, without pretending free infrastructure has perfect reliability?

### Canonical workflow

1. Fill the **Marketing Prompt Builder** in AdvertFloz and download the personalized prompt plus batch/consolidation instructions.
2. Upload the product repository directly to an external LLM; paste the prompt; generate the 365-day libraries in 13 fixed batches, then consolidate and validate.
3. Manually generate images one by one, optionally add text/logo manually, approve them, and export as actual JPEGs named `1.jpg` through `365.jpg`.
4. Put the images into a single ZIP or split ZIP parts whose names and ranges follow this PRD.
5. Import `campaign_plan.csv` and ZIP parts into AdvertFloz; optionally upload the two Markdown workbooks, `image_prompts.csv` and `campaign_manifest.json` for cross-validation.
6. Fix errors, review the contact sheet, production tracker and calendar; no generated campaign row is activated automatically.
7. Connect Facebook and Instagram in **Connections & Credentials** using the supported Meta OAuth flow; do not paste social-account passwords or tokens.
8. Pilot 30 Facebook posts in local mode and observe for 14 days.
9. Only after provider/payment, security, alerting, backup, restore and laptop-off tests pass, sync the campaign to the remote plane and activate a 30-day window.
10. Use the calendar, daily digest, external heartbeat and phone-accessible kill switch to operate safely.

### Architectural rule

**Streamlit is the control panel, never the scheduler of record.** The remote scheduler and durable remote state must run independently of the browser, Streamlit session and laptop. Local-only mode stops scheduling when its machine/process sleeps or stops.

## 1. Scope and operating modes

### 1.1 In scope

- Prompt Builder that produces an external-LLM master prompt with product brief inputs and exact output contracts; it never scans the repository itself.
- Batch-based 365-day library workflow with running continuity ledger, deterministic merge/validation tooling and fixed output filenames.
- Campaign CSV, image-prompt CSV and manifest schemas; manual-image tracker; multi-part image ZIP import; checksums; contact sheet; calendar and post inspector.
- Facebook Page connection via official Meta authorization; discovery and selection of Page name/ID; connection/test-post status.
- Instagram professional-account connection through the chosen and tested Meta flow; discover/confirm username and account ID; independent status from Facebook.
- BYOK policy for social accounts, Meta developer app credentials, remote infrastructure and notifications.
- Local 30-post Facebook pilot; later remote scheduler if Phase 0 passes.
- Token/permission lifecycle, quota preflight, alerts, Telegram pause/status, durable state, `UNKNOWN_OUTCOME` reconciliation, backups, result exports and UTM conventions.
- Static single-image feed posts as the only automatically publishable media in v1.7.

### 1.2 Out of scope

AdvertFloz source-repository upload/scanning; direct AI API calls; image generation within AdvertFloz; automated carousel/Story/Reel/video publishing; ads; DM/comment automation; scraping or browser automation; public anonymous control panel; full hosted multi-tenant SaaS/billing; unsupported/unofficial publishing APIs.

### 1.3 Operating profiles

**Local personal mode.** Streamlit + Python + SQLite on one laptop. No in-app login is acceptable only when the server binds to `127.0.0.1`/`localhost`. The user's machine is the execution host; local mode cannot publish while powered off/asleep or while its worker process is stopped. Use for development and the first Facebook-only 30-post pilot.

**Remote mode.** Streamlit is a private/authenticated control panel. A separately deployed Worker, durable DB, and media storage own scheduling and state. After a verified remote sync and activation, the user's laptop and Streamlit app can be off. This mode is conditional on Phase 0; free-tier labels do not guarantee that no payment method or no-charge usage is available.

**Self-hosted BYO mode.** The installer/deployer provides their own Meta Developer App credentials and cloud credentials through deployment secrets. End users authorize their own social accounts via OAuth. Keys are not entered in ordinary campaign CSVs or copied into Git.

**Hosted multi-user mode.** Not supported as an anonymous shared app in v1.7. Any shared-hosted deployment must have app authentication/private access. A multi-tenant public service is a separate scope requiring user identity, tenant-isolated data, per-tenant token handling, authorization checks and isolation tests.

## 2. UI/UX information architecture

Sidebar:

1. **Overview** — connection states, next due post, upcoming 48-hour preflight, image-buffer count, worker heartbeat, unresolved incidents.
2. **Marketing Prompt Builder** — product, audience, market, language, start date/timezone, channel and CTA inputs; preview/download master prompt and batch instructions.
3. **Campaign Import** — upload plan CSV and one or more ZIP parts; optional manifest/Markdown/prompt CSV; blocking errors/warnings; contact-sheet preview.
4. **Calendar** — month/week/day/agenda, platform/status/campaign filters, post card and detailed inspector.
5. **Image Production** — prompt ready → image generated → overlay done → approved → named → included in ZIP → uploaded → synced → ready.
6. **Publishing Queue** — pending, claimed, published, partial success, failed, missed and unknown outcome; attempt log and recovery actions.
7. **Facebook Page** — connect/reconnect, select Page, permissions, token health, test post, activate/pause/resume.
8. **Instagram** — connect/reconnect, chosen auth flow, discover account, format/quota/token checks, test post, activate/pause/resume.
9. **Connections & Credentials** — masked configuration status, OAuth connection state and setup instructions; secret values are never re-shown.
10. **Reliability & Incidents** — heartbeat, preflight, retries, token expiry, alerts, circuit breaker.
11. **Reports & Export** — actual-post CSV with remote ID/permalink, UTM export, failures and attempt history.
12. **Settings & Recovery** — timezone, notification setup, backup/restore, storage health and provider budget gate.

### Calendar behavior

The calendar is the primary operating screen, not a decorative month grid. It provides month/week/day/agenda views, image thumbnails, caption previews, local time and IANA timezone, target platform badges, production and publish status, row-level warning markers, filters, and click-through to a post inspector. Drag-to-reschedule is allowed only for unclaimed/unpublished future rows and must produce a diff/confirmation. Published records are immutable. A successful Facebook post does not mark Instagram published.

### Connection screen behavior

Do not show empty text fields asking the user to type Page name, Page ID, Instagram ID, Facebook password or bearer tokens. The screen has clear **Connect Facebook** and **Connect Instagram** buttons, runs OAuth, displays a returned list of authorized targets, lets the operator select one, and shows a connection test. Account names and IDs are populated by the provider; an optional human-readable label can be edited.

## 3. Meta account connection — exact user journey

### 3.1 Facebook Page

1. Operator confirms the installation's Meta App is configured and the callback URI exactly matches the Meta Developer settings.
2. Click **Connect Facebook**.
3. Browser redirects to the official Meta login/authorization page. User signs in directly with Meta and reviews the permission prompt.
4. Meta redirects to a secured backend callback. Backend validates single-use `state` (and PKCE where supported), exchanges the authorization code server-side, checks granted scopes, and queries authorized Pages.
5. UI displays available Page names and IDs. Operator selects the intended Page; Page ID is stored as immutable target metadata.
6. Backend verifies access and publishing permissions. Run a non-publishing connection check, then an explicit test-post action after user confirmation.
7. Store returned remote post ID and permalink if supplied. Do not infer success from HTTP request initiation alone.

### 3.2 Instagram

The connection wizard must tell the operator which Meta flow is configured. The preferred initial path for the pilot is a professional Instagram account linked to the selected Page, using the tested Instagram API with Facebook Login path. The wizard discovers the linked Instagram professional account and shows username/account ID. If no eligible linked professional account appears, block publishing with a clear explanation; never ask the user to paste an Instagram password or access token.

A direct Instagram Login path may be added only when independently configured and tested; it has different scopes and account-linkage rules. Phase 0 records the chosen flow and the exact current permission names. Do not conflate `instagram_content_publish` with legacy/deprecated scope names.

### 3.3 What is typed versus discovered

| Value | How it enters AdvertFloz |
|---|---|
| Facebook Page name/avatar/ID | Discovered from Meta after authorization; user selects one |
| Instagram username/account ID | Discovered through the chosen authorized flow |
| Facebook/Instagram password | Never requested, stored or logged |
| OAuth access/refresh token | Received and exchanged by backend; never shown in UI or exported |
| Granted scopes, issue/expiry time | Retrieved/validated by backend; displayed as masked metadata |
| Posting timezone/time | User selects in Settings or campaign plan |
| Meta App ID/Secret | Installation/deployment configuration, not end-user account form |
| Cloudflare/GitHub deployment token | Installer/deployer secret only; not a social-account credential |
| Telegram Bot Token | Optional installation secret; never displayed after configuration |
| Telegram chat ID | Verified and allow-listed |
| AI-provider key | Not required; external LLM is operated manually |

## 4. BYOK — ownership and secret handling

BYOK has four distinct classes. Do not label them all “account credentials”.

1. **Social-account BYOK:** each operator connects their own Page/Instagram account through OAuth. They do not paste account passwords or normal-use tokens.
2. **Meta Developer App BYOK:** the deployment owner can use their own Meta App ID/Secret. These credentials are used for OAuth and belong in deployment secrets. In a shared hosted installation, the service operator owns the Meta app configuration; users only authorize their social accounts.
3. **Infrastructure BYOK:** Cloudflare API tokens, GitHub deployment tokens, database bindings and encryption keys belong to the installation operator and are supplied through CLI/dashboard/CI secret settings—not a normal Streamlit form. Never put these in campaign data or Git.
4. **Notification BYOK:** optional Telegram bot and recipient configuration. In the single-operator profile, set token as a deployment secret and verify/allow-list chat ID. Per-tenant notification keys are out of scope until multi-tenant identity exists.

No AI-provider API key is required. Prompt creation is local template substitution; campaign production happens in an external LLM session chosen by the user.

### Secret storage requirements

- Local mode: keep secrets outside repository; `.env`/`secrets.toml` excluded by `.gitignore`; use OS keyring or encrypted local secret store where feasible. If the encryption key is stored beside ciphertext with no OS protection, document the weaker threat model and do not claim strong at-rest protection.
- Remote mode: deployment secrets in provider secret manager; user OAuth tokens stored encrypted at application layer in durable storage; encryption key stored separately as backend secret. D1 must not contain raw token plaintext. Token plaintext must not appear in logs, URLs, exceptions, exports or dashboard DOM.
- Store only metadata (platform, target ID/name, scopes, token type, `issued_at`, known `expires_at`, last validated time, status) in readable columns.
- Provide disconnect/revoke, reconnect, credential-rotation and backup-restore runbooks. Backups exclude raw secrets and ciphertext is useless without the separate key; recovery checklist must include restoring the key from the password manager/secret manager.

## 5. Master prompt and external LLM output package

AdvertFloz's Prompt Builder fills placeholders in a downloadable, vendor-portable master prompt. It does not upload repository files and does not call an LLM API. The operator then uploads the repository directly to their external LLM conversation.

The external LLM must produce an output directory with these exact final files:

```text
AdvertFloz_Campaign_Package_<campaign_slug>_<start_date>/
  README_FIRST.md
  365_day_prompt_library.md
  365_outcomes_driven_campaigns.md
  campaign_plan.csv
  image_prompts.csv
  campaign_manifest.json
  continuity_ledger.md
  campaign_validation.md
  assumptions_and_questions.md
  batches/
    365_day_prompt_library_PART_001_030.md
    365_outcomes_driven_campaigns_PART_001_030.md
    campaign_plan_PART_001_030.csv
    image_prompts_PART_001_030.csv
    ...
    *_PART_361_365.*
```

Generation is 13 fixed ranges: 001–030, 031–060, 061–090, 091–120, 121–150, 151–180, 181–210, 211–240, 241–270, 271–300, 301–330, 331–360 and 361–365. Every batch has exact file names, exact row counts, complete standalone prompts and a continuity ledger update. The final consolidation step merges all batches, checks for missing/duplicate IDs, plan-to-prompt mismatches, unsupported claims, repeated concepts and bad CSV quoting, then emits the final files above.

### 5.1 `365_day_prompt_library.md`

Each daily entry must include: Day and `post_id`; campaign chapter; audience/geographic target; objective/funnel; static image feed format and dimensions; palette including HEX values; unique core visual concept and visual grammar; complete standalone image-generation prompt; negative/avoid list; exact headline for manual typesetting; Facebook caption; Instagram caption (with link-in-bio behavior when appropriate); hashtags; CTA; destination URL/placement; `image_id`; exact `image_filename` (`42.jpg` for `image_id=42`); alt-text suggestion; verified product-truth gate; AI-disclosure review note; KPI and experiment hypothesis. The actual image binary is not generated by the LLM. Default every post to a single static image; output formats requiring multiple assets are not publishable in v1.7.

### 5.2 `365_outcomes_driven_campaigns.md`

Every day includes audience, stage, objective, hypothesis, CTA, verified/proposed destination, UTM content ID, primary and secondary KPI, experiment question, success interpretation, product-feature proof gate, privacy/safety constraints, and measurement caveats. These are plans, not fabricated performance results.

## 6. Canonical CSV contract

### 6.1 `campaign_plan.csv` — exact header

```csv
post_id,scheduled_at,timezone,platforms,image_id,caption,enabled,campaign_tag,facebook_caption,instagram_caption,alt_text,destination_url,grace_minutes,ai_disclosure_status,notes
```

Rules:

- `post_id` is `P001`–`P365`; a 30-post pilot may use a subset defined in the manifest.
- `scheduled_at` format is `YYYY-MM-DDTHH:MM:SS` local wall time; `timezone` must be a valid IANA zone, e.g. `Asia/Kolkata`, never `IST`.
- Block nonexistent/ambiguous DST times until the operator chooses a valid local time.
- `platforms` must be exactly `facebook`, `instagram`, or `facebook;instagram` in lowercase, with no spaces around the semicolon.
- `image_id` is integer 1–365; default mapping is `P042` → `image_id=42` → `42.jpg`.
- `caption` is required fallback copy. Platform-specific captions override the fallback when non-empty. Hashtags intended for publication must be present in each effective caption.
- Facebook caption may include its verified HTTPS destination link. Instagram feed caption must not claim the feed URL is clickable; use link-in-bio wording or the operator's profile link arrangement.
- `enabled` must be literal lowercase `false` in all AI-generated rows. Activation is a separate, explicit operation in AdvertFloz.
- `campaign_tag` is a stable short slug, not personal data.
- `alt_text` should describe visible content, not stuff keywords.
- `destination_url` blank or HTTPS. UTM generation, if enabled, uses only stable fields such as source, medium, campaign tag and `post_id`.
- `grace_minutes` blank or within app-configured safe bounds.
- `ai_disclosure_status`: `not_reviewed`, `not_required`, `required_pending`, `completed`. External AI defaults to `not_reviewed`; no automatic assumption that disclosure is unnecessary.
- `notes` is optional review context. Never include secrets, OAuth values or private birth/health/etc. data.
- CSV is UTF-8/RFC 4180; preserve Tamil, emoji, commas, quotes and multiline captions. `schema_version` belongs in manifest, not repeated per row.
- `first_comment` and `link_comment` are out of scope for automated publishing v1.7; do not add columns for them.

### 6.2 `image_prompts.csv` — exact header

```csv
post_id,image_id,headline,core_visual_concept,visual_grammar,prompt,negative_prompt,aspect_ratio,language,alt_text,product_claims_used
```

Exactly one row per `post_id`; `image_id` matches `campaign_plan.csv`; prompts must be standalone. No `same as above`, ellipses, placeholders or references to omitted sections.

### 6.3 `campaign_manifest.json`

Required keys: `schema_version` (`1.7`), `campaign_id`, `product_name`, `campaign_tag`, `start_date`, `end_date`, `timezone_default`, `planned_days`, `platforms`, `post_count`, `expected_post_ids`, `image_naming_pattern` (`{image_id}.jpg`), canonical filenames, `batch_ranges`, `enabled_default` (`false`) and `validation_status` (`review_required`).

## 7. Image ZIP contract — exact names and contents

The LLM creates prompts, not actual image binaries. The human generates one actual image per `image_id` and exports a real JPEG.

### Naming

- `P001` → `image_id=1` → `1.jpg`; `P042` → `image_id=42` → `42.jpg`; `P365` → `365.jpg`.
- Positive decimal IDs only: no leading zeros, prefixes, suffixes or duplicate IDs.
- A file named `.jpg` must contain actual JPEG bytes. Renaming PNG bytes to `.jpg` is invalid.
- Do not place passwords, access tokens, source repositories, prompts or unrelated files in the asset ZIP.

### Canonical ZIP names

- `advertfloz_images_001_365.zip` holds `1.jpg`–`365.jpg` at archive root.
- `advertfloz_images_001_030.zip` holds `1.jpg`–`30.jpg` at archive root.
- `advertfloz_images_031_060.zip` holds `31.jpg`–`60.jpg` at archive root.
- Continue using the same global ID/range convention through `advertfloz_images_361_365.zip`.

No nested `images/` folder, directories, nested archives, symlinks, `__MACOSX`, path traversal or unrelated files. ZIP range and contents must agree. AdvertFloz validates size, decoded JPEG, dimensions, SHA-256 and duplicate IDs across all parts. Configurable limits are shown before upload.

### Import steps

1. Upload `campaign_plan.csv`.
2. Upload one or more image ZIP parts.
3. Optionally add `image_prompts.csv`, `campaign_manifest.json` and both Markdown workbooks for cross-checking.
4. The importer extracts only to a temporary sandbox, validates safe paths and bytes, builds the explicit mapping `image_id → filename → checksum → post_id`, and creates a contact sheet.
5. It shows blocking errors and warnings. Incomplete imports cannot be activated. Resume is based on a durable import manifest and verified hashes, not duplicate uploads.

## 8. Platform constraints and preflight

Store publishing limits in a versioned registry and verify against the selected Graph API version during implementation and live connection tests. Initial conservative Instagram profile: static JPEG feed post, 4:5 through 1.91:1 aspect ratio, 8 MB file size, caption <=2,200 characters, five hashtags as conservative application policy, and live account quota checked where a supported endpoint is available. Verify all values during Phase 0; never present the remembered values as permanent Meta guarantees.

Facebook image/caption constraints are adapter-specific and versioned. Import-time checks handle deterministic constraints; T-24-hour preflight and publish-time checks handle permissions, token health, quotas, media URL and account state. Each platform's checks are independent.

## 9. Publishing and durable state

Each campaign post creates one platform job per target platform. Minimum states include `DRAFT`, `VALIDATION_BLOCKED`, `READY_FOR_REVIEW`, `APPROVED`, `SYNC_PENDING`, `SYNCED`, `QUEUED`, `CLAIMED`, `PROCESSING_MEDIA`, `PUBLISHING`, `PUBLISHED`, `FAILED_RETRYABLE`, `FAILED_PERMANENT`, `MISSED`, `UNKNOWN_OUTCOME`, `PAUSED` and `CANCELLED`.

- A remote worker claims due jobs using a durable lease/idempotency key and dispatches only activated rows whose media and credentials pass checks.
- Instagram container creation, processing checks and publishing are separate durable stages resumed across Cron ticks. Never sleep inside one invocation while waiting for media processing.
- Persist each stage, attempt ID, timestamps and provider response metadata.
- Save remote post/media ID and permalink when returned.
- If the request could have been accepted but the response is ambiguous, mark `UNKNOWN_OUTCOME`, alert and reconcile before any retry. Never blind retry.
- Each platform has independent state. One platform's success does not make the other successful.
- Missed jobs beyond grace become `MISSED`; do not silently reschedule.

## 10. Token lifecycle, alerts and phone kill switch

Record auth flow, token type, granted scopes, issued-at, known expiry and last validation. Warn T-14 days when expiry is known. Refresh only via the chosen flow's documented supported mechanism; otherwise pause the affected platform and request reauthorization.

T-24-hour preflight checks the next 48 hours of jobs, token/permission status, available quota if queryable, media URLs, worker clock, plan revision, asset buffer and notification delivery. Alert externally on permanent failures, missed/unknown jobs, expiring tokens, restrictions, missing heartbeat/digest, backup/restore failure and low image buffer.

Optional Telegram commands: `/status`, `/pause`, `/pause facebook`, `/pause instagram`, `/resume`. Only the allow-listed chat ID and valid command/webhook authentication are permitted. Pause is recorded durably before new jobs are dispatched; an already in-flight network call cannot be recalled. An independent monitor must detect stale heartbeat and missing daily digest without depending on the worker itself.

## 11. Remote architecture and ₹0 gate

Preferred remote plane after validation: Cloudflare Worker Cron for bounded scheduling, D1 for durable state, private R2 for media, Streamlit/Python as control plane, GitHub Actions for CI/test/deployment, and optional Telegram + independent monitor for alerts.

GitHub Actions is **not** the default scheduler. A GHA scheduler is a fallback only after a separate proof of concept with durable external DB/media, safe concurrency, pause, alert and recovery. Never commit live SQLite or OAuth tokens to Git.

Phase 0 must verify the actual account's R2 checkout/payment requirement, Worker usage ceilings, free-tier quotas, media accessibility, OAuth callback/domain and restore capability. If R2 is not compatible with the strict zero-spend goal, test a named alternative. Public Pages assets may be used only with explicit acceptance that future creatives can become publicly reachable; use a short rolling window. If no acceptable provider combination passes the gate, remote mode is NO-GO—use local mode while the laptop runs or Meta Business Suite/manual scheduling.

## 12. Measurement and re-import

- Generate safe UTMs from stable non-personal values such as campaign tag and `post_id`; never include sensitive personal data.
- Export `what_actually_posted.csv` with platform, post ID, scheduled/actual times, outcome, remote ID, permalink, campaign tag, URL and error category.
- Report performance metrics only from official insights/export data; never invent reach, saves, clicks or revenue.
- Use `post_id` as immutable identity. Published rows and attempts are locked. Re-import future rows shows a field-by-field diff before applying. Claimed/in-flight payloads cannot change until reconciled.
- At least 14 consecutive days of approved and synced assets are required before normal activation; activate at most the next 30 days by default. No rows without assets can be activated.

## 13. Security and privacy

- No passwords; no plaintext tokens in UI, DB, logs, URLs, CSV, Markdown, ZIP, backup or Git.
- Validate OAuth state/callback and permissions; exchange code server-side; redact Authorization headers and token response bodies.
- Local no-login only on loopback; hosted panel private/authenticated. Multi-user hosting requires tenant-level auth and isolation before release.
- Infrastructure keys live in deployment secret storage. Remote OAuth tokens are application-encrypted at rest; encryption key is stored separately.
- Protect ZIP extraction against traversal, nested archives, symlinks and expanded-size exhaustion. Treat uploaded text as untrusted and never execute it.
- Audit connection, disconnection, target changes, activation, pause/resume, plan revisions, token errors and publish attempts.

## 14. Non-functional requirements

| ID | Requirement | Acceptance target |
|---|---|---|
| NFR-01 | Import performance | 365-row CSV + 365 JPEGs totaling <=250 MB: local validation/contact sheet target <=60 seconds on modern 4-core/8-GB laptop; benchmark actual hardware. |
| NFR-02 | Local capacity | At least 2 GB free or 3x largest bundle, whichever is greater. |
| NFR-03 | OS | Windows 10/11 x64 and supported Ubuntu/Debian Linux; macOS best-effort until tested. |
| NFR-04 | Worker bounds | Small bounded work per Cron tick; no sleeps/unbounded loops; persist Instagram stage transitions. |
| NFR-05 | Timing | Best effort within Cron interval plus provider latency; no exact-second SLA. |
| NFR-06 | Observability | Show heartbeat, last platform success, oldest job, next post, asset buffer, incidents and latest backup. |
| NFR-07 | Logs | Rotate daily/retain 30 days locally; redact secrets. Remote history campaign life + 90 days unless exported. |
| NFR-08 | Restore | Secret-free backups and restore drill before remote launch, then monthly. |
| NFR-09 | Accessibility | Keyboard controls, semantic labels, readable contrast and text status (not color-only). |
| NFR-10 | Integrity | SHA-256 per image and campaign revision; result tied to revision/post/platform. |
| NFR-11 | Limits | Configurable import/archive ceilings shown before upload. |
| NFR-12 | Cost safety | No auto-upgrade; warn and hard-stop before usage causes unexpected spend. |
| NFR-13 | Credentials | No client-visible token values; encrypted remote tokens and separate key. |

## 15. Implementation phases

**Phase 0 — feasibility gates:** configure/test real Meta app, callback, Pages discovery, scopes, token lifecycle, target selection, test post, R2 payment/setup, Worker limits, notification route and restore. Record Facebook, Instagram, storage and remote scheduler go/no-go separately.

**Phase 1 — external prompt/files:** Prompt Builder, master prompt, continuation/consolidation contract, exact schemas, validator and fixtures.

**Phase 2 — importer/tracker/calendar:** CSV and ZIP validation, contact sheet, production tracker, month/week/day/agenda, inspector and safe re-import.

**Phase 3 — Facebook local thin slice:** 30 posts, one Page, real connection/test publish, durable local state and visible failure handling; observe 14 days.

**Phase 4 — remote sync/storage:** only after budget gate; authenticated API, media sync, hashes, encrypted token persistence, backup/restore.

**Phase 5 — remote worker/alerts:** bounded Cron state machine, leases, heartbeat, Telegram controls, preflight and laptop-off canary.

**Phase 6 — Instagram:** chosen official flow, media URL, quota, token and asynchronous publish-state tests. Keep disabled until it passes.

**Phase 7 — hardening:** full fault-injection/restore tests, no-duplicate reconciliation, restriction circuit breaker, controlled 30-day production windows.

## 16. Functional requirements — canonical register

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-001 | Prompt Builder | Inputs create downloadable external-LLM prompt; no repository received by AdvertFloz. |
| FR-002 | Output contract | Prompt defines exact Markdown, CSV, manifest, batches and ZIP naming. |
| FR-003 | Batch continuation | 13 fixed ranges and cumulative continuity ledger. |
| FR-004 | Merge/validator | Detect missing/duplicate IDs, bad headers, drift, placeholders and near duplicates. |
| FR-005 | Plan CSV import | Strict header, enums, dates and row-level errors. |
| FR-006 | Image ZIP import | Numeric mapping, safe extraction, checksums, MIME/decoded JPEG. |
| FR-007 | Contact sheet | Bounded thumbnails linked to post/image IDs. |
| FR-008 | Production tracker | Per-asset prompt through upload/sync/readiness status. |
| FR-009 | Calendar | Month/week/day/agenda, filters and inspector. |
| FR-010 | Revision safety | Diff preview; lock published/in-flight payloads. |
| FR-011 | Facebook OAuth | Discover/select Page, validate permission and test post. |
| FR-012 | Instagram connection | Chosen official flow, professional account discovery and eligibility test. |
| FR-013 | BYOK ownership | Separate social OAuth from app/cloud/notification secrets; no AI key. |
| FR-014 | Secret protection | No plaintext tokens; encrypt remote OAuth tokens and separate encryption key. |
| FR-015 | Local safety | No login only on loopback and visible laptop-availability warning. |
| FR-016 | Hosted access | Hosted controls private/authenticated; anonymous public control fails release gate. |
| FR-017 | Remote sync | Revision and active-window assets verified before remote activation. |
| FR-018 | Durable scheduler | Leases/idempotency prevent overlapping sends; record each transition. |
| FR-019 | Instagram state machine | Create/process/publish stages resume across ticks. |
| FR-020 | Retry policy | Classify retryable/permanent/missed/unknown; reconcile ambiguity first. |
| FR-021 | Platform independence | Separate jobs and status; independent pause/activation. |
| FR-022 | Token lifecycle | Flow/scopes/expiry, T-14 alert, supported refresh and reconnect. |
| FR-023 | Preflight | T-24h next-48h checks for tokens, assets, quota, worker and alerts. |
| FR-024 | External alerts | Fail/miss/unknown/token/buffer/worker/backup alerts and independent daily digest. |
| FR-025 | Phone kill switch | Authorized Telegram status/pause/resume commands. |
| FR-026 | Activation gate | >=14 days assets; <=30-day activation window default. |
| FR-027 | Reporting | Actual-post CSV with remote ID/permalink; no invented metrics. |
| FR-028 | Restriction circuit breaker | Pause affected platform on restrictions/repeated integrity errors. |
| FR-029 | Recovery | Secret-free backups, key recovery runbook, restore tests. |
| FR-030 | Cost gate | Verify payment/quotas; no auto-upgrade; remote no-go if strict budget fails. |
| FR-031 | Native fallback | Meta Business Suite/manual scheduling runbook; no assumed import/horizon. |
| FR-032 | Audit/health | Show heartbeat, next job, last success, queue, incidents and backups. |

## 17. Fault-test register

Release tests must include: missing/extra CSV column; duplicate post ID; `enabled=yes`; invalid timezone/datetime; DST gap/overlap; Tamil/emoji/multiline caption; caption >2,200; missing image; duplicate image ID across ZIPs; leading-zero filename; PNG renamed `.jpg`; corrupt JPEG; ZIP traversal/zip bomb; interrupted upload/hash mismatch; contact-sheet memory limit; published/future-row re-import conflict; app restart; Streamlit hibernation; laptop-off local mode; stale Cron heartbeat; Worker CPU/subrequest limit; database/media outage; R2 payment requirement; fallback pause; Meta media-fetch error; expiring token; unsupported refresh; revoked scope; rate limit; Instagram processing stage; ambiguous publish result; duplicate Cron; partial FB/IG success; missed grace; Telegram wrong chat/webhook; pause while queued/in-flight; missing daily digest; lost account/2FA recovery; restore mismatch; Meta restriction; anonymous hosted control panel; OAuth state mismatch/replay; callback URI mismatch; Page target mismatch; no linked Instagram account; App Secret leakage; missing deployment secret; output filename/schema drift; missing continuity ledger; ZIP range mismatch; disconnect/revoke.

## 18. Definition of done

- Master prompt, output contract, schemas, ZIP notes, templates and validator agree on all filenames and mapping.
- OAuth wizard distinguishes user social accounts from installation/deployment keys.
- No password/raw token form and no token display.
- 30-post import maps every image deterministically and blocks incomplete activation.
- Published/in-flight history cannot be overwritten by re-import.
- Facebook local pilot succeeds and is observed for 14 days.
- Remote mode passes payment/provider gate, laptop-off, alert, pause, restore and no-duplicate tests.
- Instagram separately passes account, media, quota, token and async state tests before it is enabled.
