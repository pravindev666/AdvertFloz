# AdvertFloz v1.7 package QA report

## Automated package checks completed

- Python compilation passed for both validator scripts.
- Every CSV template/fixture parsed using Python's CSV reader; headers align with the v1.7 plan/prompt contract.
- JSON manifest example parses and declares `schema_version=1.7`, `{image_id}.jpg`, and `enabled_default=false`.
- Import-validator smoke test passed against a two-row CSV, a temporary ZIP containing root-level numeric JPEG-signature assets, and the manifest example: 0 blocking errors, 0 warnings.
- Canonical mapping is consistent: `P042` → `image_id=42` → `42.jpg`.
- Connection documentation separates the user's social OAuth from deployment-owned Meta App, Cloudflare/GitHub and Telegram secrets.
- A repository-wide version-consistency scan was completed; the new package uses one canonical v1.7 contract.

## Not claimed by these checks

- No live Meta OAuth authorization or permission grant was performed.
- No Facebook or Instagram post was published by this document-generation process.
- No Cloudflare resources were configured/deployed.
- No guarantee is made about R2 payment requirements, free-tier availability, provider uptime or exact post timing.
- Test archive was temporary and is not part of the user deliverable. Actual images must be generated and reviewed by the user.

## Go/no-go gate

Run Phase 0 with the actual Meta Developer App, Facebook Page, Instagram account and remote provider. Record independent go/no-go for Facebook, Instagram, media storage and unattended remote publishing.
