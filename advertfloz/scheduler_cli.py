"""Command-line entry point for the bounded scheduler.

Streamlit is not the scheduler of record. Run this from Windows Task Scheduler, cron or
systemd. Each call performs bounded work and exits.

    python -m advertfloz.scheduler_cli tick --once
    python -m advertfloz.scheduler_cli tick --limit 5
    python -m advertfloz.scheduler_cli digest
    python -m advertfloz.scheduler_cli status
"""
from __future__ import annotations

import argparse
import json
import sys

from .application.services.notifications import build_daily_digest, emit_digest
from .config import load_settings
from .infrastructure.notifications.telegram import TelegramBot, TelegramConfig
from .infrastructure.persistence.local_sqlite import Repository
from .infrastructure.scheduler import heartbeat_stale, run_once
from .infrastructure.security.redaction import install_redacting_logging


def _repo(settings) -> Repository:
    return Repository(settings.db_path)


def cmd_tick(args) -> int:
    settings = load_settings()
    repo = _repo(settings)
    try:
        run = run_once(repo, settings, limit=args.limit, emit_daily_digest=args.digest)
        result = {
            "claimed": run.tick.claimed,
            "published": run.tick.published,
            "deferred": run.tick.deferred,
            "missed": run.tick.missed,
            "unknown": run.tick.unknown,
            "failed_permanent": run.tick.failed_permanent,
            "paused_skipped": run.tick.paused_skipped,
            "heartbeat_at": run.heartbeat_at,
            "incidents": len(run.incidents),
            "digest_sent": run.digest_sent,
        }
        print(json.dumps(result, indent=2))
        return 0
    finally:
        repo.close()


def cmd_digest(args) -> int:
    settings = load_settings()
    repo = _repo(settings)
    try:
        bot = TelegramBot(
            TelegramConfig(
                settings.secret("TELEGRAM_BOT_TOKEN"),
                settings.telegram_allowed_chat_id,
                settings.secret("TELEGRAM_WEBHOOK_SECRET"),
            )
        )
        if not bot.config.configured:
            print(build_daily_digest(repo))
            print("\n[alert channel not configured — digest printed only]")
            return 0
        sent, detail = emit_digest(repo, bot)
        print(f"digest sent={sent} detail={detail}")
        return 0 if sent else 1
    finally:
        repo.close()


def cmd_status(args) -> int:
    settings = load_settings()
    repo = _repo(settings)
    try:
        print(json.dumps({
            "mode": settings.mode,
            "job_counts": repo.count_jobs_by_status(),
            "unknown_outcomes": repo.unknown_outcome_count(),
            "heartbeat_stale": heartbeat_stale(repo),
            "paused_all": repo.get_flag("pause_all") == "1",
            "paused_facebook": repo.get_flag("pause_facebook") == "1",
            "paused_instagram": repo.get_flag("pause_instagram") == "1",
        }, indent=2))
        return 0
    finally:
        repo.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="advertfloz.scheduler_cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    tick = sub.add_parser("tick", help="Run one bounded scheduling tick")
    tick.add_argument("--once", action="store_true", help="run a single tick (default)")
    tick.add_argument("--limit", type=int, default=5, help="max jobs per tick")
    tick.add_argument("--digest", action="store_true", help="also emit the daily digest")
    tick.set_defaults(func=cmd_tick)

    digest = sub.add_parser("digest", help="Emit the daily health digest")
    digest.set_defaults(func=cmd_digest)

    status = sub.add_parser("status", help="Print scheduler/job status")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    install_redacting_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
