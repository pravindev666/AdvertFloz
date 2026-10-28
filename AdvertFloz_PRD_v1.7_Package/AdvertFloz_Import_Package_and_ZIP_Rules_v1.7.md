# AdvertFloz Import Package and ZIP Rules v1.7

## Required inputs

- `campaign_plan.csv`
- one or more `advertfloz_images_NNN_NNN.zip` archives

Optional cross-check inputs: `image_prompts.csv`, `campaign_manifest.json`, `365_day_prompt_library.md`, `365_outcomes_driven_campaigns.md`.

## Deterministic mapping

`P001` → `image_id=1` → `1.jpg`  
`P042` → `image_id=42` → `42.jpg`  
`P365` → `image_id=365` → `365.jpg`

ZIP ordering is never used to match images. IDs are global across all ZIP parts.

## Canonical ZIP names

| ZIP file | Contents at archive root |
|---|---|
| `advertfloz_images_001_365.zip` | `1.jpg` ... `365.jpg` |
| `advertfloz_images_001_030.zip` | `1.jpg` ... `30.jpg` |
| `advertfloz_images_031_060.zip` | `31.jpg` ... `60.jpg` |
| `advertfloz_images_061_090.zip` | `61.jpg` ... `90.jpg` |
| `advertfloz_images_091_120.zip` | `91.jpg` ... `120.jpg` |
| `advertfloz_images_121_150.zip` | `121.jpg` ... `150.jpg` |
| `advertfloz_images_151_180.zip` | `151.jpg` ... `180.jpg` |
| `advertfloz_images_181_210.zip` | `181.jpg` ... `210.jpg` |
| `advertfloz_images_211_240.zip` | `211.jpg` ... `240.jpg` |
| `advertfloz_images_241_270.zip` | `241.jpg` ... `270.jpg` |
| `advertfloz_images_271_300.zip` | `271.jpg` ... `300.jpg` |
| `advertfloz_images_301_330.zip` | `301.jpg` ... `330.jpg` |
| `advertfloz_images_331_360.zip` | `331.jpg` ... `360.jpg` |
| `advertfloz_images_361_365.zip` | `361.jpg` ... `365.jpg` |

The importer may allow a custom contiguous range only if the ZIP name and every contained ID agree. Canonical ranges are recommended.

## Rules

- Filenames are positive decimal numbers with no leading zero, prefix or suffix: `42.jpg`, not `042.jpg`, `IMG-042.jpg`, `P042.jpg` or `42-final.jpg`.
- `.jpg` must contain actual JPEG bytes. Do not simply rename a PNG to `.jpg`; export/convert it to JPEG first.
- Archives are flat; no nested directory, hidden OS metadata, unrelated files, scripts, symlinks, nested archives or path traversal.
- Importer checks name, range, magic bytes, decodability, dimensions, file size, total expanded bytes and SHA-256. Duplicate IDs across ZIPs block activation.
- ZIP only final approved images, not CSVs, prompts, repositories or credentials.
- A campaign can be partially imported for preparation, but the active window remains blocked until every required image exists, passes validation and is synced remotely.
