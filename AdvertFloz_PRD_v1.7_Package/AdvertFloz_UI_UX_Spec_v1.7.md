# AdvertFloz UI/UX Specification v1.7

## UX goals

- Explain the next action in plain language; never assume the user understands OAuth, tokens or media containers.
- Separate account connection, campaign import and cloud deployment credentials.
- Never show a green “connected” badge as equivalent to “can publish”. Connection, permission test and real test post are separate states.
- Show Facebook and Instagram status independently.
- Local no-login mode is only valid on `127.0.0.1`/`localhost`. Hosted control panels must be private/authenticated.

## Sidebar

1. Overview
2. Marketing Prompt Builder
3. Campaign Import
4. Calendar
5. Image Production
6. Publishing Queue
7. Facebook Page
8. Instagram
9. Connections & Credentials
10. Reliability & Incidents
11. Reports & Export
12. Settings & Recovery

## First-run wizard

### A. Choose mode

**Local laptop:** simplest for the 30-post pilot; local scheduling stops when laptop or process stops.  
**Remote unattended:** requires separately configured scheduler, database, media storage, alerts and tested restore. Show payment/free-tier checks before enabling setup.

### B. Meta App configuration

Show only `Configured / Missing`, the allowed callback URI and setup instructions. The installation operator configures Meta App ID/Secret in deployment secrets; never show Secret after configuration and never ask an end user to paste it into an ordinary form. `Connect` is disabled if app/callback settings are missing.

### C. Facebook Page connection

Button: **Connect Facebook**. Help text: “You will sign in on Meta's official page. AdvertFloz never asks for your Facebook password.”

After authorization, backend validates `state`, exchanges the code server-side, checks scopes and returns eligible Pages. The UI then shows a dropdown containing returned Page name and Page ID. User selects one and clicks **Test connection**. A separate **Publish test post** action requires confirmation and stores remote ID/permalink. Changing selected Page requires confirmation; do not silently retarget queued jobs.

States: Not connected, Authorization pending, Connected—Page not selected, Page selected, Permission missing, Test passed, Reconnect required, Paused/restricted.

### D. Instagram connection

Button: **Connect Instagram**. Explain the selected auth path and account eligibility before redirecting. Initial path prefers a professional Instagram account linked to the selected Facebook Page. If discovered, show username/ID and require confirmation. If none is found, show setup guidance and keep Instagram disabled; never request an Instagram password or raw token. Direct Instagram Login may be shown only if configured and separately tested.

### E. Notifications

Optional Telegram setup. Bot token is configured as a backend/deployment secret; UI shows only `Configured / Missing`. Verify an authorized chat ID and send a test alert. Wrong chat IDs must not operate commands.

### F. Readiness gate

Separate readiness checklist per platform: app/callback configured, OAuth successful, target selected, scopes granted, token status known, test post confirmed, media method verified, alert test passed, remote storage/sync/backup ready (remote mode). Show `Ready for local pilot`, `Ready for remote canary`, or `Not ready`.

## Marketing Prompt Builder

Fields: product/brand, website, markets, audience(s), languages, tone, campaign start date, posting time, IANA timezone, cadence, intended platforms, primary outcome, verified destination URLs, features to verify, claims to avoid, campaign tag, art direction, optional notes. Buttons: **Download master prompt**, **Download batch/consolidation instructions**, **Download output contract**. Prominent note: “Upload the source repository to your chosen external AI yourself. AdvertFloz does not receive or scan it.”

## Campaign Import

Required uploads: `campaign_plan.csv` and one or more `advertfloz_images_NNN_NNN.zip` archives. Optional validation artifacts: `image_prompts.csv`, `campaign_manifest.json`, `365_day_prompt_library.md`, `365_outcomes_driven_campaigns.md`.

Show upload limits before starting. Validate all ZIP parts as one logical set. Interrupted import stores a checkpoint and resumes from verified hashes. Display blocking errors separately from warnings: CSV schema, bad dates/timezone/DST, invalid `enabled`, missing/duplicate images, wrong ZIP range, non-JPEG bytes, checksum/file size, caption limit, link/claim/disclosure warning.

Build a contact sheet where every tile shows `image_id`, filename, `post_id` and production status. Do not activate partial imports.

## Calendar

Views: month, week, day, agenda. Controls: previous/next/today, timezone, platform/status/campaign/production filters. Cards show post ID, thumbnail, local time, platform chips and a text status.

Post inspector contains image preview/hash, two platform captions, scheduled time/timezone, CTA/destination, image prompt reference, alt text, claim/disclosure review, attempt timeline, API remote ID/permalink and error category. Actions: edit future row, reschedule, pause one platform job, inspect error, reconcile unknown outcome. Published content is read-only except annotations. Reschedule produces a confirmation and validates grace/timezone/collision.

## Image Production

Status sequence: Prompt ready → Generated → Overlay done → Approved → Correct filename → Included in ZIP → Uploaded → Synced → Ready to activate. Display count of approved/synced images ahead per platform/date. Warn below 21 days; block normal activation below 14 consecutive days. No row activates without an approved, synced image.

## Platform panels

Each Facebook/Instagram page independently shows target name and ID, auth flow, scopes status, token health/expiry metadata, last test post, last successful publish, quota verification where available, queued/failed counts, activation window and pause/resume/reconnect/disconnect controls.

Pause confirmation distinguishes one platform versus all platforms. If a publish call is already in flight, explain that it cannot be recalled; the durable pause prevents subsequent dispatches.

## Connections & Credentials

Groups:
- **Social accounts:** official Meta OAuth, no password/token field.
- **Meta Developer App:** deployment admin configures App ID/Secret in secret settings; UI only reports ready/missing and callback URI.
- **Cloud/infrastructure:** configured by installer through dashboard/CLI/CI secret settings, never general text input.
- **Notifications:** bot token masked; recipient chat verified.
- **AI provider:** no API key required; external manual workflow.

Offer disconnect/reconnect and links to credential-recovery instructions. Never provide a “reveal saved token” control.

## Reliability & Incidents

Top strip: remote heartbeat age, last successful publish per channel, next post, oldest queued job, preflight status, asset buffer, latest backup and unresolved `UNKNOWN_OUTCOME`. Alerts have severity, post ID, platform, cause, timestamp, safe action and retry/pause state. A missing daily digest is itself an incident; absence of errors alone is not health proof.

## Reports

Download `what_actually_posted.csv` with one row per platform outcome: post ID, platform, scheduled/actual time, status, remote ID/permalink, campaign tag, destination and error. Performance metrics appear only when imported from a real supported source.

## Accessibility/security

Keyboard usable; focus visible; contrast adequate; status text never color-only; descriptive labels; confirmation for destructive and target-changing actions; untrusted text rendered safely; no token values in visible UI or logs.
