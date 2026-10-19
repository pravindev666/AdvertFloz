"""Restore a secret-free backup bundle.

    python scripts/restore.py --backup backups/<id> --target data/restored.sqlite

After restoring, put the separate TOKEN_ENCRYPTION_KEY back in place (or reconnect platforms
if the key is lost). Never fabricate a token.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from advertfloz.application.services.backups import restore_backup  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    result = restore_backup(args.backup, args.target, overwrite=args.overwrite)
    print(result.message)
    if result.ok and result.needs_reauth:
        print("NOTE: tokens need the original TOKEN_ENCRYPTION_KEY, or platforms must be reconnected.")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
