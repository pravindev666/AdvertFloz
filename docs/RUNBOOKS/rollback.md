# Runbook — rollback and incident recovery

## Emergency pause

- UI: Settings/Queue → **Emergency pause (all)**.
- Telegram (if configured): `/pause all` from the allow-listed chat.
- API/CLI: `POST /api/control/pause?target=all` on the Worker, or set `pause_all=1`.

A pause is durable before new dispatch. Calls already in flight cannot be recalled.

## Roll back a release

1. Stop the Streamlit app and the local scheduler.
2. Restore the previous application version (git checkout of the prior tag/commit).
3. Restore the database only if a migration was applied: `python scripts/restore.py --backup <id>
   --target data/advertfloz.sqlite --overwrite`. Migrations are forward-only and not destructive, so
   a schema restore is normally unnecessary.
4. Run `python scripts/doctor.py`.
5. Resume platforms deliberately.

## Roll back the remote Worker

```bash
cd worker
npx wrangler deployments list
npx wrangler rollback <deployment-id>
```

The Worker holds no campaign state in Git; D1 retains durable state.

## Reconcile an UNKNOWN_OUTCOME

1. Open **Publishing Queue**, filter `UNKNOWN_OUTCOME`.
2. Check the provider (Page/IG) for the post manually.
3. If it was published, record the remote ID/permalink and mark it resolved — do not re-send.
4. If it was not published, only then requeue. Blind retry is never offered.

## Recover from a restriction circuit breaker

The affected platform is paused. Review the account in Meta, resolve the policy issue, then
resume. Rows remain `PAUSED` until you resume.
