# AdvertFloz v1.7

A single-operator campaign control plane: a Streamlit/Python application that builds an
external-LLM prompt, imports a 365-day campaign package (CSV + image ZIP parts), tracks manual
image production, and publishes single-image feed posts to a Facebook Page and Instagram
professional account through Meta's official APIs — plus a Cloudflare Worker remote scheduler
for laptop-off operation.

**Streamlit is the control plane, never the scheduler of record.** Local scheduling is a
separate bounded process; remote scheduling is the Worker.

## What this repository contains

```
advertfloz/
  streamlit_app.py            Streamlit entry point (st.navigation)
  advertfloz/                 Python package
    config.py                 Settings, fail-closed hosted auth, secret handling
    domain/                   enums, models, validation rules, scheduling, idempotency, UTM
    application/services/     prompt builder, import, revisions, activation, publishing engine, ...
    infrastructure/           SQLite persistence, Meta adapters, storage, notifications, security, scheduler
    oauth_callback/app.py     local-mode Meta OAuth callback service (loopback)
    diagnostics.py            doctor + zero-cost gate
    scheduler_cli.py          bounded scheduler CLI
    ui/                       navigation, theme, components, 12 pages + first-run wizard
  worker/                     Cloudflare Worker remote plane (TypeScript, D1, R2, Cron)
  tests/                      unit / integration / contract / security / e2e
  tools/                      the supplied v1.7 validators (vendored, unmodified semantics)
  scripts/                    migrate, backup, restore, doctor, cost_gate
  docs/                       status, decisions, ADR, provider compatibility, threat model, runbooks
```

## Quick start (local mode, Windows or Linux)

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # Linux

# 1. Reconcile the database schema
python scripts/migrate.py

# 2. See what is configured (never prints secret values)
python scripts/doctor.py

# 3. Run the control plane
streamlit run streamlit_app.py

# 4. Run the scheduler separately (Task Scheduler / cron), NOT inside Streamlit
python -m advertfloz.scheduler_cli tick --once
python -m advertfloz.scheduler_cli digest
```

Local mode binds to `127.0.0.1` only. It publishes only while this machine and the scheduler
process are running — that limitation is shown in the UI at all times.

## Configuration

Copy `.env.example` to `.env` (gitignored) or use `.streamlit/secrets.toml` (gitignored) or
your OS keyring. Secret values are never displayed, logged or exported. See
`docs/RUNBOOKS/credential_recovery.md` for which secrets exist and where they belong.

Generate a token encryption key:

```bash
python -m advertfloz.infrastructure.security.crypto genkey
```

## Demo mode

Set `ADVERTFLOZ_MODE=demo` to exercise the whole flow with clearly-labelled fixtures and the
mock provider. Demo mode never claims a live provider success; the UI labels demo connections
as demo.

## Meta app and OAuth callback

Two explicit callback topologies (see `docs/ADR-v1.7-implementation.md`):

- Local mode: `http://localhost:8765/oauth/meta/callback`, served by
  `uvicorn advertfloz.oauth_callback.app:app --host 127.0.0.1 --port 8765`. Valid only when the
  browser and this service run on the same machine.
- Remote mode: `https://<worker-domain>/oauth/meta/callback`, served by the Cloudflare Worker.
  Streamlit Community Cloud is never the callback backend.

## Remote plane (conditional)

Remote mode is **NO-GO until the zero-cost gate passes**. Check it any time:

```bash
python scripts/cost_gate.py
```

If the R2 payment prerequisite, quotas, media retrieval, auth or restore checks fail, remote
stays disabled and local mode keeps working. No paid fallback is ever enabled automatically.

## Tests

```bash
ruff check advertfloz tests scripts
pytest -q
python tools/validate_campaign_package_v1.7.py --csv tests/fixtures/AdvertFloz_fixture_valid_edge_cases_v1.7.csv --zip <part>.zip
cd worker && npm install && npx tsc --noEmit && npx vitest run
```

## Never do this

- Never enter a Facebook/Instagram password in AdvertFloz. There is no such field.
- Never paste raw OAuth tokens, the Meta App Secret, Cloudflare tokens or the Telegram bot token
  into CSV/Markdown/ZIP/Git.
- Never use an anonymous public hosted control panel with publishing controls.
- Never blindly retry an `UNKNOWN_OUTCOME`; reconcile with the provider first.
