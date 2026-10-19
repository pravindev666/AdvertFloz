# AdvertFloz v1.7 — Decisions

Material ambiguities and genuine contradictions found while implementing the v1.7 package. Each
entry records the conservative decision taken and the references/tests updated with it. This file
is not used to weaken accepted requirements.

## D-001 — Supplied "valid" fixture had a malformed row

**Finding.** `AdvertFloz_fixture_valid_edge_cases_v1.7.csv`, row `P002`, contained 14 fields for
the 15-column plan header. The multiline Tamil/emoji caption row was missing the comma for the
(empty) `grace_minutes` field, so the supplied validator correctly reported
`invalid ai_disclosure_status` and `grace_minutes must be blank or integer 0-1440` for that row.

**Decision (conservative).** The row was intended to demonstrate UTF-8 + emoji + multiline
preservation with an empty `grace_minutes`. The working copy in `tests/fixtures/` has the missing
comma restored (`Tamil and emoji sample,,,not_reviewed,...`). The CSV header, semantics and every
other row are unchanged. The unmodified defect is recorded here rather than being silently
discarded.

**Updated together.** `tests/fixtures/AdvertFloz_fixture_valid_edge_cases_v1.7.csv`,
`tests/test_vendored_validators.py`.

## D-002 — `advertfloz` is a nested package inside the repository

The layout in the build instruction shows `advertfloz/streamlit_app.py` at the repository root.
To make `python -m advertfloz.scheduler_cli` and `uvicorn advertfloz.oauth_callback.app:app`
work without shadowing installed top-level names (`config`, `domain`, …), the Python package is
nested one level: repository root `advertfloz/` contains `advertfloz/`, `worker/`, `tests/`,
`scripts/`, `tools/`, `docs/`. `streamlit_app.py` lives at the repository root and inserts the
root on `sys.path`. Responsibility separation from the instruction is preserved exactly.

## D-003 — ZIP/image validation lives under `infrastructure/storage`

The build instruction lists `application/services/zip_validation.py`. It was placed at
`infrastructure/storage/zip_validation.py` because it is an archive/byte-level adapter, and the
import orchestration stays in `application/services/campaign_import.py`. Behaviour and contract
are unchanged.

## D-004 — Ambiguous provider responses are never "success"

`GraphResponse.ok` is false when a response is flagged ambiguous or when a body is unparseable.
This follows PRD §7.3/§9: uncertainty is not equivalent to success or failure, and such rows become
`UNKNOWN_OUTCOME` and are reconciled before any retry.

## D-005 — Remote OAuth callback is the Worker, never localhost

Localhost callback services are not assumed reachable in hosted mode. Local mode uses the loopback
`oauth_callback` service; remote mode uses the Worker endpoint. See `ADR-v1.7-implementation.md`.

## D-006 — `str, Enum` is intentional

Domain enums inherit from `str, Enum` (not `StrEnum`) so their JSON and log representation is
stable across Python 3.11+. The `UP042` lint rule is disabled for this reason.

## D-007 — Media must be fetchable by Meta over HTTPS

Real publishing requires a public HTTPS base URL for media (`ADVERTFLOZ_MEDIA_BASE_URL` or signed
R2 URLs from the Worker). Without it, the media-fetch diagnostic and the zero-cost gate report
BLOCKED, and publishing is not presented as possible.
