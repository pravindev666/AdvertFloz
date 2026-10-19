# AdvertFloz External LLM Output Contract v1.7

This contract is authoritative for campaign artifacts created by ChatGPT or another LLM after the user uploads their product repository to that separate AI conversation. AdvertFloz does not ingest the repository and does not generate actual image binaries.

## Final package directory and filenames

```text
AdvertFloz_Campaign_Package_<campaign_slug>_<YYYY-MM-DD>/
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
    ...all 13 fixed ranges...
```

## Batches

Generate 13 ranges exactly: `001_030`, `031_060`, `061_090`, `091_120`, `121_150`, `151_180`, `181_210`, `211_240`, `241_270`, `271_300`, `301_330`, `331_360`, `361_365`. One range per AI turn. Every batch includes two Markdown parts and two CSV parts with exact row counts, plus an updated cumulative ledger and checklist. Consolidation merges batches numerically and detects missing/duplicate IDs, schema mismatch, CSV/Markdown drift, unverified claims and likely duplicates.

## `campaign_plan.csv` exact header

```csv
post_id,scheduled_at,timezone,platforms,image_id,caption,enabled,campaign_tag,facebook_caption,instagram_caption,alt_text,destination_url,grace_minutes,ai_disclosure_status,notes
```

## `image_prompts.csv` exact header

```csv
post_id,image_id,headline,core_visual_concept,visual_grammar,prompt,negative_prompt,aspect_ratio,language,alt_text,product_claims_used
```

## Rules for every row

- Day 001 = `post_id=P001`, `image_id=1`, `image_filename=1.jpg`; day 042 = `P042`, `42`, `42.jpg`; day 365 = `P365`, `365`, `365.jpg`.
- `enabled` is the literal lowercase string `false` for every AI-generated row.
- `platforms` is `facebook`, `instagram`, or `facebook;instagram` exactly.
- `scheduled_at` is `YYYY-MM-DDTHH:MM:SS`; `timezone` is a valid IANA name such as `Asia/Kolkata`, not `IST`. Use user-supplied campaign start/timezone and flag DST gaps/overlaps.
- Generic `caption` is required fallback copy. Populate Facebook/Instagram caption overrides with platform-appropriate text. Put hashtags intended for publishing in the actual captions.
- Instagram feed captions must not claim a URL is clickable in-feed; use link-in-bio language when appropriate. Use verified HTTPS URLs only.
- `ai_disclosure_status` defaults to `not_reviewed`; do not assume disclosure is unnecessary.
- `grace_minutes` stays blank unless explicitly specified and sensible.
- Use UTF-8/RFC 4180 CSV quoting; preserve Tamil, emoji, commas, quotes and multiline captions.
- No credentials or secrets in files. No personal/sensitive data in UTM parameters.
- Static single-image feed only for importable rows in v1.7. Do not represent a carousel/Reel/Story as if one JPEG were sufficient.

## `365_day_prompt_library.md`

Every day must contain: day number, post ID, campaign chapter, audience/geography/language, goal/funnel, single-image format and dimensions, palette/HEX, unique visual concept and visual grammar, complete standalone image-generation prompt, negative prompt, exact headline to typeset manually, Facebook caption, Instagram caption, hashtags, CTA, verified destination/link placement, image ID/exact filename, alt-text idea, product-truth gate, AI-disclosure review, KPI and experiment hypothesis. The user will generate the actual image separately; do not claim an image binary exists.

## `365_outcomes_driven_campaigns.md`

Every daily entry includes audience, objective, hypothesis, funnel stage, CTA, verified/proposed destination, UTM content ID based on post ID, KPI(s), test/learning question, success interpretation, product claim proof gate and privacy/safety checks. KPIs are plans, never fabricated outcomes.

## `campaign_manifest.json`

Required keys: `schema_version` (`1.7`), `campaign_id`, `product_name`, `campaign_tag`, `start_date`, `end_date`, `timezone_default`, `planned_days`, `platforms`, `post_count`, `expected_post_ids`, `image_naming_pattern` (`{image_id}.jpg`), canonical filenames, `batch_ranges`, `enabled_default` (`false`), `validation_status` (`review_required`).

## Continuity ledger and quality control

Record completed/next ranges, used topics, hooks, concepts, visual grammars, palette frequency, audience coverage, CTAs/destinations, claims needing proof, prohibited repeats, near-duplicate pairs and unresolved assumptions. Carry it forward cumulatively. No `TODO`, `TBD`, “same as above”, “see above”, ellipses, placeholder prompts or intentionally omitted content.

## User-generated image ZIPs are separate

The LLM package has no real images. After manually generating actual JPEG assets, user creates `advertfloz_images_001_030.zip` containing `1.jpg`–`30.jpg` at archive root; similar global-ID ranges continue for each ZIP part. Full year may be `advertfloz_images_001_365.zip`. No nested folder inside the archive. Do not rename PNG bytes as JPG; export/convert to real JPEG first.

## Final validation checklist

- Both final Markdown workbooks have exactly Day 001–365 in order.
- Both CSVs have exactly 365 rows, unique IDs and exact headers.
- IDs, dates, captions, destination and filenames agree across all artifacts.
- All `enabled=false`; manifest says `enabled_default: false`.
- Product claims/URLs are grounded or explicitly labelled for operator review.
- Duplicate/near-duplicate candidates are recorded.
- CSV preserves UTF-8 and quoted multiline content.
- The package clearly states the user must manually generate and ZIP actual images.
