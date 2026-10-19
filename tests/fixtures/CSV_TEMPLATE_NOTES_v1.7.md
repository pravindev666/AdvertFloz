# CSV template notes v1.7

- Exact plan headers: `post_id,scheduled_at,timezone,platforms,image_id,caption,enabled,campaign_tag,facebook_caption,instagram_caption,alt_text,destination_url,grace_minutes,ai_disclosure_status,notes`.
- Exact prompt headers: `post_id,image_id,headline,core_visual_concept,visual_grammar,prompt,negative_prompt,aspect_ratio,language,alt_text,product_claims_used`.
- External AI rows must set `enabled=false`; activation is controlled in the app.
- `P042` maps to `image_id=42` and `42.jpg`; ZIP order is irrelevant.
- `schema_version` belongs in `campaign_manifest.json`, not a repeated CSV column.
- `platforms` accepts only lowercase `facebook`, `instagram` or `facebook;instagram`.
- Use UTF-8/RFC 4180 quoting and preserve Tamil, emoji, commas, quotes and multiline captions.
- `destination_url` must be blank or verified HTTPS. The example `example.com` is illustrative only.
- No social password, access token, Meta App Secret, Cloudflare key or Telegram bot token belongs in campaign files.
