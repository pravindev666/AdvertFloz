"""Tests for master password and hosted gate authentication."""
from __future__ import annotations

from advertfloz.config import load_settings


def test_admin_password_configured_detected():
    settings = load_settings({"ADVERTFLOZ_ADMIN_PASSWORD": "supersecretpassword123"})
    assert settings.admin_password_configured is True
    assert settings.secret("ADVERTFLOZ_ADMIN_PASSWORD") == "supersecretpassword123"
    # Never exposed in redacted()
    assert "supersecretpassword123" not in str(settings.redacted())
    assert settings.redacted()["admin_password_configured"] is True


def test_admin_password_not_configured_by_default():
    settings = load_settings({})
    assert settings.admin_password_configured is False
    assert settings.secret("ADVERTFLOZ_ADMIN_PASSWORD") == ""
    assert settings.redacted()["admin_password_configured"] is False


def test_hosted_auth_ready_with_password():
    # If hosted is true, admin_password satisfies hosted_auth_ready
    settings = load_settings({"ADVERTFLOZ_HOSTED": "1", "ADVERTFLOZ_ADMIN_PASSWORD": "mypassword"})
    assert settings.hosted is True
    assert settings.hosted_auth_ready() is True
