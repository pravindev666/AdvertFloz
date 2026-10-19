"""Unit tests for UTM generation and idempotency keys."""
from __future__ import annotations

import pytest

from advertfloz.domain.enums import Platform
from advertfloz.domain.idempotency import job_identity, job_key
from advertfloz.domain.utm import build_utm


def test_idempotency_key_stable_and_formatted():
    assert job_key("camp", 2, "P001", Platform.FACEBOOK) == "camp:2:P001:facebook"
    assert job_identity("camp", 2, "P001", "instagram") == ("camp", 2, "P001", "instagram")


def test_idempotency_rejects_separator_in_components():
    with pytest.raises(ValueError):
        job_key("cam:p", 1, "P001", Platform.FACEBOOK)


def test_utm_uses_stable_non_personal_fields():
    url = build_utm("https://example.com/signup", "musikflo_2027", "P042")
    assert "utm_campaign=musikflo_2027" in url
    assert "utm_content=P042" in url
    assert "utm_source=advertfloz" in url


def test_utm_requires_https():
    with pytest.raises(ValueError):
        build_utm("http://example.com", "tag", "P001")


def test_utm_rejects_personal_data():
    with pytest.raises(ValueError):
        build_utm("https://example.com", "tag@example.com", "P001")
