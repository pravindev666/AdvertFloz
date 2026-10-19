"""Headless UI smoke tests: every page renders without exceptions (UI acceptance, light checks).

Uses Streamlit's AppTest to execute each page as a script, which is how Streamlit runs them in a
real app. This catches import-time and render-time errors that a plain import would miss.
"""
from __future__ import annotations

from pathlib import Path

import pytest

streamlit = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    "overview.py",
    "prompt_builder.py",
    "campaign_import.py",
    "calendar.py",
    "image_production.py",
    "publishing_queue.py",
    "facebook_page.py",
    "instagram.py",
    "connections.py",
    "reliability.py",
    "reports.py",
    "settings.py",
    "first_run_wizard.py",
]


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVERTFLOZ_DB_PATH", str(tmp_path / "ui.sqlite"))
    monkeypatch.setenv("ADVERTFLOZ_MODE", "demo")
    yield


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exception(page: str):
    path = ROOT / "advertfloz" / "ui" / "pages" / page
    app = AppTest.from_file(str(path), default_timeout=30)
    app.run()
    assert not app.exception, [e.message for e in app.exception]


def test_navigation_registers_all_pages():
    from advertfloz.ui.navigation import PAGES as NAV_PAGES

    assert "Overview" in NAV_PAGES
    assert {"Marketing Prompt Builder", "Campaign Import", "Calendar", "Settings & Recovery"} <= set(NAV_PAGES)
    assert len(NAV_PAGES) == 13
