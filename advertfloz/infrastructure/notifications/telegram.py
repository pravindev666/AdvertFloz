"""Telegram alert + emergency-command channel (FR-024, FR-025).

The bot token lives only in backend secret config. Commands are accepted only from the
allow-listed chat id, are rate limited, and every command writes an audit event. The chat id
is an identifier, not a credential.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field

ALLOWED_COMMANDS = {
    "/status",
    "/pause",
    "/pause facebook",
    "/pause instagram",
    "/pause all",
    "/resume facebook",
    "/resume instagram",
    "/resume all",
    "/resume",
}

RATE_LIMIT_SECONDS = 2


@dataclass
class TelegramConfig:
    bot_token: str = ""
    allowed_chat_id: str = ""
    webhook_secret: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.bot_token and self.allowed_chat_id)


@dataclass
class CommandResult:
    accepted: bool
    action: str = ""       # status | pause | resume
    target: str = ""       # all | facebook | instagram
    reply: str = ""
    reason: str = ""


@dataclass
class TelegramBot:
    config: TelegramConfig
    _last_command_at: dict[str, float] = field(default_factory=dict)

    def is_authorized(self, chat_id: str) -> bool:
        return bool(self.config.allowed_chat_id) and str(chat_id) == str(self.config.allowed_chat_id)

    def verify_webhook_secret(self, header_value: str) -> bool:
        """Constant-time compare of the Telegram secret-token header."""
        if not self.config.webhook_secret:
            return False
        return hmac.compare_digest(header_value or "", self.config.webhook_secret)

    def _rate_limited(self, chat_id: str) -> bool:
        last = self._last_command_at.get(chat_id, 0.0)
        if time.monotonic() - last < RATE_LIMIT_SECONDS:
            return True
        self._last_command_at[chat_id] = time.monotonic()
        return False

    def parse_command(self, chat_id: str, text: str) -> CommandResult:
        if not self.is_authorized(chat_id):
            return CommandResult(False, reason="unauthorized chat id")
        if self._rate_limited(chat_id):
            return CommandResult(False, reason="rate limited")
        command = " ".join((text or "").strip().lower().split())
        if command not in ALLOWED_COMMANDS:
            return CommandResult(False, reason=f"unsupported command {command!r}")
        if command == "/status":
            return CommandResult(True, "status", "", "Status requested.")
        parts = command.split()
        verb = parts[0].lstrip("/")
        target = parts[1] if len(parts) > 1 else "all"
        return CommandResult(True, verb, target, f"{verb} {target} recorded; an in-flight call cannot be recalled.")

    def send(self, text: str) -> tuple[bool, str]:
        """Send a message. Without configured credentials this reports a precise blocker."""
        if not self.config.configured:
            return False, "Telegram is not configured (bot token + allow-listed chat id required)."
        import requests

        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        try:
            resp = requests.post(url, json={"chat_id": self.config.allowed_chat_id, "text": text[:4000]}, timeout=15)
            return (resp.status_code == 200, f"status={resp.status_code}")
        except Exception as exc:
            return False, f"send failed: {type(exc).__name__}"


def sign_payload(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
