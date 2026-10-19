"""Security tests: Telegram allow-list, rate limiting, and webhook secret checks (FR-025)."""
from __future__ import annotations

from advertfloz.infrastructure.notifications.telegram import TelegramBot, TelegramConfig


def bot() -> TelegramBot:
    return TelegramBot(TelegramConfig("token", "12345", "webhook-secret"))


def test_authorized_status_command():
    result = bot().parse_command("12345", "/status")
    assert result.accepted and result.action == "status"


def test_unauthorized_chat_is_rejected():
    result = bot().parse_command("99999", "/pause all")
    assert not result.accepted
    assert "unauthorized" in result.reason


def test_unknown_command_rejected():
    result = bot().parse_command("12345", "/shutdown")
    assert not result.accepted


def test_rate_limit_blocks_rapid_commands():
    instance = bot()
    assert instance.parse_command("12345", "/status").accepted
    assert not instance.parse_command("12345", "/status").accepted


def test_pause_targets_parsed():
    instance = bot()
    result = instance.parse_command("12345", "/pause instagram")
    assert result.accepted
    assert result.action == "pause"
    assert result.target == "instagram"


def test_webhook_secret_verification():
    instance = bot()
    assert instance.verify_webhook_secret("webhook-secret")
    assert not instance.verify_webhook_secret("wrong")
    assert not TelegramBot(TelegramConfig("t", "1", "")).verify_webhook_secret("")


def test_send_reports_blocker_when_unconfigured():
    sent, detail = TelegramBot(TelegramConfig()).send("hello")
    assert not sent
    assert "not configured" in detail
