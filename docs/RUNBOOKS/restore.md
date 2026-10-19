# Runbook — backup and restore

## Create a backup

```bash
python scripts/backup.py --dest backups
python scripts/backup.py --dest backups --include-media --media-dir data/media
```

Backups are **secret-free**. The database contains only OAuth token ciphertext, which is useless
without the separately stored `TOKEN_ENCRYPTION_KEY`.

## Restore

```bash
python scripts/restore.py --backup backups/<backup-id> --target data/advertfloz.sqlite
```

The restore verifies the database SHA-256 from the bundle manifest and refuses to overwrite an
existing target unless `--overwrite` is given.

## After restoring

1. Restore `TOKEN_ENCRYPTION_KEY` from your secret manager.
2. If the key is unavailable, tokens cannot be decrypted — reconnect each platform instead.
3. Run `python scripts/doctor.py` and confirm migrations are current.
4. Record a restore drill in Settings & Recovery so freshness is visible on the Overview.

## Monthly drill

Run a restore into a throwaway path, start the app against it, and confirm connections and queue
state. A backup that has never been restored is not a verified backup.
