"""Apply database migrations. Safe to run repeatedly; never destructive.

    python scripts/migrate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from advertfloz.config import load_settings  # noqa: E402
from advertfloz.infrastructure.persistence.local_sqlite import Repository  # noqa: E402
from advertfloz.infrastructure.persistence.local_sqlite.migrations import SCHEMA_VERSION, current_version  # noqa: E402


def main() -> int:
    settings = load_settings()
    repo = Repository(settings.db_path)  # Repository applies migrations on open
    try:
        print(f"Database: {settings.db_path}")
        print(f"Schema version: {current_version(repo.conn)} (target {SCHEMA_VERSION})")
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    raise SystemExit(main())
