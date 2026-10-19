"""Create a secret-free backup bundle.

    python scripts/backup.py [--dest backups] [--include-media]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from advertfloz.application.services.backups import create_backup  # noqa: E402
from advertfloz.config import load_settings  # noqa: E402
from advertfloz.infrastructure.persistence.local_sqlite import Repository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", default="backups")
    parser.add_argument("--include-media", action="store_true")
    parser.add_argument("--media-dir", default="data/media")
    args = parser.parse_args()

    settings = load_settings()
    repo = Repository(settings.db_path)
    try:
        run = create_backup(repo, args.dest, include_media=args.include_media, media_dir=args.media_dir)
        print(f"Backup written: {run.path} ({run.byte_size} bytes, includes_secrets={run.includes_secrets})")
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    raise SystemExit(main())
