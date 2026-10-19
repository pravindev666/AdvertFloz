"""Redaction of secrets from logs, error messages and diagnostics.

Anything that could carry a credential — Authorization headers, OAuth ``code`` query
parameters, access tokens, bot tokens or our own configured secrets — is masked before it
reaches a log file, an exception surfaced to the UI, or an export.
"""
from __future__ import annotations

import logging
import re

MASK = "***REDACTED***"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?\S+"), r"\1" + MASK),
    (re.compile(r"(?i)(access_token=)[^&\s]+"), r"\1" + MASK),
    (re.compile(r"(?i)(refresh_token=)[^&\s]+"), r"\1" + MASK),
    (re.compile(r"(?i)(client_secret=)[^&\s]+"), r"\1" + MASK),
    (re.compile(r"(?i)(code=)[A-Za-z0-9._\-]+"), r"\1" + MASK),
    (re.compile(r"(?i)(bot)?\d{6,}:[A-Za-z0-9_\-]{10,}"), MASK),   # telegram bot token
    (re.compile(r"EAA[A-Za-z0-9]{20,}"), MASK),                      # Meta access token prefix
]


def redact(text: str) -> str:
    """Return ``text`` with any recognizable credential masked."""
    if not text:
        return text
    out = str(text)
    for pattern, replacement in _PATTERNS:
        out = pattern.sub(replacement, out)
    return out


class RedactingFilter(logging.Filter):
    """Logging filter that masks secrets in the rendered message and args."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:  # pragma: no cover - never let logging break the app
            pass
        return True


def install_redacting_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
