# AdvertFloz v1.7 — Implementation status

Two evidence columns are kept deliberately separate:

- **Mock evidence** — the test or command that proves the code path works offline.
- **Live acceptance** — set to `PASS` only by an actually-executed live test against real
  accounts. Compiling code or passing mocks never sets a live row to PASS. Until then rows are
  `PENDING (external Phase 0)`.

Status values: `COMPLETE` (implemented + tested offline) · `PARTIAL` · `BLOCKED`.

## Functional requirements

| ID | Requirement | Status | Implementation path | Mock evidence | Live acceptance |
|---|---|---|---|---|---|
| FR-001 | Prompt Builder | COMPLETE | `application/services/prompt_builder.py`, `ui/pages/prompt_builder.py` | `tests/unit/test_prompt_builder.py` | n/a (local only) |
| FR-002 | Output contract | COMPLETE | `templates/`, `prompt_builder.build_output_contract` | `test_prompt_builder.py::test_master_prompt_contains_contract_requirements` | n/a |
| FR-003 | Batch continuation (13 ranges) | COMPLETE | `domain/validation_rules.BATCH_RANGES`, `prompt_builder.build_batch_continuation_prompt` | `test_prompt_builder.py::test_batch_and_contract_available` | n/a |
| FR-004 | Merge/validator | COMPLETE | `tools/validate_campaign_batches_v1.7.py` (vendored) | `tests/test_vendored_validators.py` | n/a |
| FR-005 | Plan CSV import | COMPLETE | `application/services/campaign_import.py`, `domain/validation_rules.py` | `tests/unit/test_validation_rules.py`, `tests/test_vendored_validators.py` | n/a |
| FR-006 | Image ZIP import | COMPLETE | `infrastructure/storage/zip_validation.py`, `local_store.py` | `tests/unit/test_zip_validation.py` | n/a |
| FR-007 | Contact sheet | COMPLETE | `application/services/contact_sheet.py` | `tests/unit/test_zip_validation.py` (decoder), `e2e` | n/a |
| FR-008 | Production tracker | COMPLETE | `ui/pages/image_production.py`, `domain/enums.ProductionState` | `tests/e2e/test_local_pipeline.py` (approve/sync) | n/a |
| FR-009 | Calendar + inspector | COMPLETE | `ui/pages/calendar.py` | UI render checks (manual) | n/a |
| FR-010 | Revision safety / re-import | COMPLETE | `application/services/reimport.py`, `campaign_revision.py` | `tests/integration/test_reimport.py` | n/a |
| FR-011 | Facebook OAuth + test post | COMPLETE (mock) | `infrastructure/meta/oauth.py`, `facebook_pages.py`, `oauth_callback/app.py` | `tests/contract/test_meta_error_classification.py`, `tests/integration/test_oauth_callback_service.py` | PENDING (external Phase 0) |
| FR-012 | Instagram connection | COMPLETE (mock) | `infrastructure/meta/instagram_publish.py`, `ui/pages/instagram.py` | `tests/integration/test_instagram_state_machine.py` | PENDING (external Phase 0) |
| FR-013 | BYOK ownership separation | COMPLETE | `config.py`, `ui/pages/connections.py`, `infrastructure/security/` | `tests/security/test_token_isolation.py` | n/a |
| FR-014 | Secret protection (AEAD) | COMPLETE | `infrastructure/security/crypto.py` | `tests/unit/test_crypto_redaction.py` | n/a |
| FR-015 | Local safety (loopback, banner) | COMPLETE | `ui/components/notify.py`, `.streamlit/config.toml` | UI render checks | n/a |
| FR-016 | Hosted access fail-closed | COMPLETE | `ui/runtime.py::enforce_hosted_gate`, `config.py` | `scripts/doctor.py` demonstrates BLOCKED when hosted without auth | n/a |
| FR-017 | Remote sync before activation | PARTIAL | `application/services/activation.py`, `worker/src/media/r2.ts` | `tests/integration/test_activation.py::test_remote_requires_sync_and_alerts` | PENDING (no R2/Worker account) |
| FR-018 | Durable scheduler (leases) | COMPLETE | `application/services/publish_orchestrator.py`, `worker/src/scheduler/tick.ts` | `tests/integration/test_publish_orchestrator.py::test_duplicate_claim_is_prevented` | PENDING (Worker deploy) |
| FR-019 | Instagram state machine | COMPLETE | `instagram_publish.py`, `publish_orchestrator.py`, `worker/src/scheduler/tick.ts` | `tests/integration/test_instagram_state_machine.py` | PENDING (external Phase 0) |
| FR-020 | Retry policy | COMPLETE | `publish_orchestrator.apply_error`, `meta/graph_client.classify_graph_error` | `tests/contract/test_meta_error_classification.py`, orchestrator tests | n/a |
| FR-021 | Platform independence | COMPLETE | separate jobs/state; per-platform pause | `test_publish_orchestrator.py::test_facebook_independent_from_instagram` | n/a |
| FR-022 | Token lifecycle (T−14) | COMPLETE | `application/services/token_lifecycle.py` | covered by `health`/`preflight` logic | PENDING (real expiry metadata) |
| FR-023 | Preflight (next 48h) | COMPLETE | `application/services/preflight.py` | exercised via `ui/pages/reliability.py` | PENDING (real quota endpoint) |
| FR-024 | External alerts + digest | COMPLETE (mock) | `application/services/notifications.py`, `infrastructure/notifications/telegram.py` | `tests/security/test_telegram_authorization.py` | PENDING (no bot configured) |
| FR-025 | Phone kill switch | COMPLETE (mock) | `telegram.py`, `worker/src/notifications/telegram.ts` | `tests/security/test_telegram_authorization.py` | PENDING (no bot configured) |
| FR-026 | Activation gate | COMPLETE | `application/services/activation.py` | `tests/integration/test_activation.py` | n/a |
| FR-027 | Reporting | COMPLETE | `application/services/reporting.py`, `ui/pages/reports.py` | `tests/e2e/test_local_pipeline.py` | n/a |
| FR-028 | Restriction circuit breaker | COMPLETE | `publish_orchestrator.apply_error` (RESTRICTION) | `test_publish_orchestrator.py::test_restriction_pauses_platform` | n/a |
| FR-029 | Recovery (backups/restore) | COMPLETE | `application/services/backups.py`, `scripts/backup.py`, `scripts/restore.py` | `tests/integration/test_backup_restore.py` | PENDING (real restore drill) |
| FR-030 | Cost gate | COMPLETE | `diagnostics.run_cost_gate`, `scripts/cost_gate.py` | `scripts/cost_gate.py` prints NO-GO | PENDING (real provider account) |
| FR-031 | Native fallback runbook | COMPLETE | `docs/RUNBOOKS/meta_native_fallback.md` | docs | n/a |
| FR-032 | Audit/health | COMPLETE | `application/services/health.py`, `incidents.py`, `ui/pages/reliability.py` | `tests/e2e/test_local_pipeline.py`, scheduler CLI `status` | n/a |

## Non-functional requirements

| ID | Requirement | Status | Mock evidence | Live acceptance |
|---|---|---|---|---|
| NFR-01 | Import performance (≤60 s for 365 rows + 365 JPEGs ≤250 MB) | PARTIAL — bounded decode verified; full-scale benchmark pending hardware | `tests/unit/test_zip_validation.py` | PENDING (benchmark) |
| NFR-02 | Local capacity | COMPLETE (limits enforced) | `scripts/doctor.py` | n/a |
| NFR-03 | OS (Windows/Linux; macOS best-effort) | PARTIAL — exercised on Windows | this environment | PENDING (Linux/macOS run) |
| NFR-04 | Worker bounds (no sleeps) | COMPLETE | `worker/src/scheduler/tick.ts`; `npx tsc --noEmit` clean; `npx vitest run` 11 passed; `npx wrangler deploy --dry-run` bundled 31.93 KiB | PENDING (Worker deploy) |
| NFR-05 | Timing best-effort | COMPLETE (documented) | docs | n/a |
| NFR-06 | Observability | COMPLETE | `health.build_overview`, `ui/pages/reliability.py` | n/a |
| NFR-07 | Log rotation / redaction (30 days) | COMPLETE (redaction) | `infrastructure/security/redaction.py`, `test_crypto_redaction.py` | n/a |
| NFR-08 | Secret-free backups + drill | COMPLETE | `test_backup_restore.py` | PENDING (drill on real data) |
| NFR-09 | Accessibility (keyboard, contrast, text status) | PARTIAL — semantics/labels present; manual audit pending | UI components (`status_badge` icon+label) | PENDING (manual audit) |
| NFR-10 | Integrity (SHA-256 per image + revision) | COMPLETE | `zip_validation`, `campaign_revision.manifest_hash` | n/a |
| NFR-11 | Configurable import ceilings | COMPLETE | `ImportLimits`, `.env.example` | n/a |
| NFR-12 | Cost safety (no auto-upgrade) | COMPLETE | `run_cost_gate` | n/a |
| NFR-13 | Credentials (no client-visible tokens) | COMPLETE | `tests/security/test_token_isolation.py` | n/a |

## Commands run (offline verification)

```
python -m ruff check advertfloz tests scripts        -> All checks passed
python -m pytest -q                                  -> 117 passed
python scripts/migrate.py                            -> Schema version 2 (target 2)
python scripts/doctor.py                             -> Overall: WARNING (expected without secrets)
python scripts/cost_gate.py                          -> Decision: NO-GO (expected without provider account)
python -m advertfloz.scheduler_cli status            -> OK
python -m advertfloz.scheduler_cli tick --once       -> OK (records heartbeat, raises missing-digest incident)
python tools/validate_campaign_package_v1.7.py ...   -> exercised by tests/test_vendored_validators.py
streamlit AppTest over all 13 pages                  -> tests/test_ui_smoke.py, 0 render exceptions
local OAuth callback topology (FastAPI TestClient)   -> tests/integration/test_oauth_callback_service.py, 6 passed
cd worker && npx tsc --noEmit                        -> clean
cd worker && npx vitest run                          -> 11 passed (service auth, remote OAuth callback, crypto)
cd worker && npx wrangler deploy --dry-run           -> Total Upload 31.93 KiB (dry run, nothing deployed)
```

## External blockers (Phase 0)

- Meta Developer App / Facebook Page / Instagram professional account — no live OAuth, no live post.
- Cloudflare account, Worker deployment, D1, R2 (R2 payment prerequisite unverified) — remote is NO-GO.
- Telegram bot + allow-listed chat — alerting untested live.
- Linux/macOS run, full-scale import benchmark, and accessibility audit — pending.

**Implementation is complete for the local plane; live-provider acceptance is pending.**
