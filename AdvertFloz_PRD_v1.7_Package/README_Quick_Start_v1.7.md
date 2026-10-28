# AdvertFloz v1.7 — Quick Start

## 1. Create the campaign plan outside AdvertFloz

1. Open AdvertFloz → **Marketing Prompt Builder** and enter product, audience, market, language, campaign start date, time, timezone, cadence, platforms, CTA and verified URL details.
2. Download the master prompt and batch/consolidation prompt.
3. Upload the product repository directly to ChatGPT or your chosen external LLM and paste the master prompt.
4. Generate the 13 batches (12 x 30 days, final batch 5 days), then consolidate into the final Markdown files and CSVs.

## 2. Generate images manually

1. Open `365_day_prompt_library.md`.
2. For each day, copy its standalone image prompt into your chosen image tool.
3. Manually add approved headline/logo overlays if needed; inspect the actual image.
4. Export actual JPEGs named `1.jpg`, `2.jpg`, …, `365.jpg`.
5. Create flat ZIP archives named by global image range; e.g. `advertfloz_images_001_030.zip` contains `1.jpg`–`30.jpg` directly at archive root.

## 3. Import into AdvertFloz

1. Upload `campaign_plan.csv` and all needed image ZIP parts.
2. Optionally add `image_prompts.csv`, `campaign_manifest.json` and both Markdown workbooks for cross-checking.
3. Fix all blocking errors; inspect the contact sheet, Image Production tracker and calendar.
4. Generated CSV rows must say `enabled=false`; activate only in the UI after approval.

## 4. Connect your social accounts

- Go to Connections & Credentials → **Connect Facebook**.
- Sign in at Meta's official authorization page; do not type your Facebook password into AdvertFloz.
- Select the Page from the returned list, test permissions and publish a confirmed test post.
- Connect Instagram separately. The initial linked-account path requires an eligible Instagram professional account linked to the selected Page. If it is not discovered, keep Instagram disabled until the proper flow is configured.

## 5. Pilot then remote mode

First run a 30-post Facebook-only local pilot and observe it for 14 days. Local mode stops when the laptop/process is off. Remote mode is allowed only after provider/billing, sync, test publish, heartbeat, alert, pause and restore checks pass.

## Never do this

- Never enter Facebook/Instagram passwords in AdvertFloz.
- Never put access tokens, Meta App Secret, Cloudflare token or Telegram bot token in CSV/Markdown/ZIP/Git.
- Never use an anonymous public hosted control panel with publishing controls.
- Never blindly retry `UNKNOWN_OUTCOME`; reconcile on Meta first.
