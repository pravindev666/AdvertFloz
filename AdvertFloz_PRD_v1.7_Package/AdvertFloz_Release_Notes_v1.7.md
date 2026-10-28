# AdvertFloz Release Notes v1.7

## Reason for release

Prior revisions described credentials and imports conceptually but did not give the implementer and end user one exact connection and package contract. v1.7 aligns account connection, BYOK, output generation, filenames, CSVs, ZIP contents, UI and recovery instructions.

## Changes

- Official Meta OAuth journey and Page/account selection UI.
- Distinction between end-user social authorization and installation-level Meta App/cloud/Telegram credentials.
- Prohibition on FB/IG password entry and normal raw-token paste.
- Hosted control plane must be private/authenticated; local no-login restricted to loopback.
- Exact external-LLM output directory, two Markdown books, CSV headers, manifest requirements and 13 batch ranges.
- Exact deterministic mapping `P042` → `image_id=42` → `42.jpg` and range-based ZIP naming.
- Updated calendar/connection wizard, account-health, token handling and remote-mode readiness gates.
- Included validators and import fixtures aligned with the v1.7 contract.

## Explicitly not delivered

No application implementation, live OAuth callback, Meta app review, live post, cloud resource deployment or guarantee of no-cost provider access is included. These require a Phase 0 test with the real accounts and deployment.
