"""Unit tests for the Prompt Builder (FR-001, FR-002, FR-003)."""
from __future__ import annotations

from advertfloz.application.services.prompt_builder import (
    BriefInputs,
    build_batch_continuation_prompt,
    build_master_prompt,
    build_output_contract,
    validate_brief,
)


def valid_brief() -> BriefInputs:
    return BriefInputs(
        product_name="MusikFlo",
        product_url="https://musikflo.example",
        target_markets="India",
        campaign_start_date="2027-01-01",
        campaign_tag="musikflo_2027",
        timezone="Asia/Kolkata",
        destination_urls="https://musikflo.example/signup",
    )


def test_validation_requires_fields():
    result = validate_brief(BriefInputs())
    assert not result.ok
    assert any("product_name" in e for e in result.errors)


def test_validation_rejects_bad_url_and_timezone():
    brief = valid_brief()
    brief.product_url = "http://insecure"
    brief.timezone = "IST"
    result = validate_brief(brief)
    assert any("https" in e for e in result.errors)
    assert any("IANA" in e for e in result.errors)


def test_master_prompt_substitutes_all_placeholders():
    prompt = build_master_prompt(valid_brief())
    assert "{{PRODUCT_NAME}}" not in prompt
    assert "MusikFlo" in prompt
    assert "Asia/Kolkata" in prompt


def test_master_prompt_contains_contract_requirements():
    prompt = build_master_prompt(valid_brief())
    assert "001_030" in prompt or "001–030" in prompt
    assert "post_id,scheduled_at,timezone,platforms,image_id,caption,enabled" in prompt
    assert "campaign_manifest.json" in prompt


def test_batch_and_contract_available():
    assert "001–030" in build_batch_continuation_prompt()
    assert "campaign_plan.csv" in build_output_contract()
