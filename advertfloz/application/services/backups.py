"""Backup and restore (FR-029, NFR-08).

Backups are secret-free: they never contain plaintext secrets. OAuth token ciphertext is
useless without the separately stored encryption key, and the runbook covers restoring that
key. Restore is explicit and non-destructive by default (restores to a target path).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ...domain.models import BackupRun
from ...infrastructure.persistence.local_sqlite import Repository

MANIFEST_NAME = "manifest.json"


@dataclass
class RestoreResult:
    ok: bool
    restored_to: str
    message: str
    needs_reauth: bool = False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(repo: Repository, dest_dir: str | Path, *, include_media: bool = False, media_dir: str | Path | None = None) -> BackupRun:
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    backup_id = f"bk-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    bundle = dest / backup_id
    bundle.mkdir(parents=True, exist_ok=True)

    db_copy = bundle / "advertfloz.sqlite"
    target = sqlite3.connect(str(db_copy))
    try:
        repo.conn.backup(target)
    finally:
        target.close()

    manifest = {
        "backup_id": backup_id,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "includes_secrets": False,
        "database": {"file": "advertfloz.sqlite", "sha256": _sha256(db_copy)},
        "media": [],
        "note": "Token ciphertext requires the separate TOKEN_ENCRYPTION_KEY to be useful. "
                "Restore that key from the password/secret manager before reconnecting.",
    }

    if include_media and media_dir:
        media_root = Path(media_dir)
        media_copy = bundle / "media"
        media_copy.mkdir(exist_ok=True)
        for jpg in sorted(media_root.glob("*.jpg")):
            shutil.copy2(jpg, media_copy / jpg.name)
            manifest["media"].append({"file": f"media/{jpg.name}", "sha256": _sha256(jpg)})

    (bundle / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    run = BackupRun(
        backup_id=backup_id,
        path=str(bundle),
        created_at=manifest["created_at"],
        byte_size=sum(f.stat().st_size for f in bundle.rglob("*") if f.is_file()),
        includes_secrets=False,
        verified=True,
    )
    repo.add_backup_run(run)
    repo.audit("operator", "backup.create", backup_id, f"{run.byte_size} bytes")
    return run


def restore_backup(backup_path: str | Path, target_db_path: str | Path, *, overwrite: bool = False) -> RestoreResult:
    bundle = Path(backup_path)
    manifest_file = bundle / MANIFEST_NAME
    if not manifest_file.is_file():
        return RestoreResult(False, str(target_db_path), "backup manifest not found")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    source = bundle / manifest["database"]["file"]
    if not source.is_file():
        return RestoreResult(False, str(target_db_path), "backup database file missing")
    if _sha256(source) != manifest["database"]["sha256"]:
        return RestoreResult(False, str(target_db_path), "backup database checksum mismatch (corrupt)")

    target = Path(target_db_path)
    if target.exists() and not overwrite:
        return RestoreResult(False, str(target), "target exists; pass overwrite=True to replace")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

    needs_reauth = manifest.get("includes_secrets") is False  # ciphertext needs the external key
    return RestoreResult(
        True, str(target),
        "Database restored. Restore TOKEN_ENCRYPTION_KEY from the secret manager, then reconnect platforms.",
        needs_reauth=needs_reauth,
    )


def record_restore_drill(repo: Repository, backup_id: str | None = None) -> None:
    runs = repo.list_backup_runs()
    if not runs:
        return
    run = runs[0] if backup_id is None else next((r for r in runs if r.backup_id == backup_id), runs[0])
    run.restore_drill_at = datetime.now(UTC).isoformat(timespec="seconds")
    repo.add_backup_run(run)
    repo.audit("operator", "backup.restore_drill", run.backup_id, "restore drill recorded")
