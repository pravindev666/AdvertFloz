"""Dependency diagnostics. Reports OK / WARNING / BLOCKED per dependency without echoing secrets.

    python scripts/doctor.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from advertfloz.config import load_settings  # noqa: E402
from advertfloz.diagnostics import run_doctor  # noqa: E402
from advertfloz.infrastructure.persistence.local_sqlite import Repository  # noqa: E402


def main() -> int:
    settings = load_settings()
    repo = Repository(settings.db_path)
    try:
        checks = run_doctor(settings, repo)
    finally:
        repo.close()
    worst = 0
    for check in checks:
        print(f"[{check.status.value:7}] {check.name:18} {check.detail}")
        worst = max(worst, {"OK": 0, "WARNING": 1, "BLOCKED": 2}[check.status.value])
    print(f"\nMode: {settings.mode} | Overall: {['OK', 'WARNING', 'BLOCKED'][worst]}")
    return 1 if worst == 2 else 0


if __name__ == "__main__":
    raise SystemExit(main())
