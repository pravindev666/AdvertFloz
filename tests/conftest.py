"""Shared pytest fixtures for AdvertFloz tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from advertfloz.infrastructure.persistence.local_sqlite import Repository


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    repository = Repository(tmp_path / "test.sqlite")
    yield repository
    repository.close()


@pytest.fixture
def fixture_dir() -> Path:
    return Path(__file__).parent / "fixtures"
