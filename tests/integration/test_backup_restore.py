"""Integration test: secret-free backup and restore, including the missing-key reauth path."""
from __future__ import annotations

from pathlib import Path

from advertfloz.application.services import backups
from tests.builders import seed_campaign


def test_backup_is_secret_free_and_restorable(repo, tmp_path: Path):
    seed_campaign(repo)
    run = backups.create_backup(repo, tmp_path / "backups")
    assert run.includes_secrets is False
    assert Path(run.path, "manifest.json").is_file()

    restore = backups.restore_backup(run.path, tmp_path / "restored.sqlite")
    assert restore.ok
    assert restore.needs_reauth is True  # ciphertext needs the separate key

    restored = backups.restore_backup(run.path, tmp_path / "restored.sqlite")
    assert not restored.ok  # refuses to overwrite without explicit flag
    restored = backups.restore_backup(run.path, tmp_path / "restored.sqlite", overwrite=True)
    assert restored.ok


def test_restore_detects_corruption(repo, tmp_path: Path):
    seed_campaign(repo)
    run = backups.create_backup(repo, tmp_path / "backups")
    db_file = Path(run.path) / "advertfloz.sqlite"
    db_file.write_bytes(b"corrupted")
    result = backups.restore_backup(run.path, tmp_path / "out.sqlite")
    assert not result.ok
    assert "checksum" in result.message


def test_restore_drill_recorded(repo, tmp_path: Path):
    seed_campaign(repo)
    run = backups.create_backup(repo, tmp_path / "backups")
    backups.record_restore_drill(repo, run.backup_id)
    assert repo.list_backup_runs()[0].restore_drill_at
