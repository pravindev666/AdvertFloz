"""Marketing Prompt Builder (FR-001). Produces downloadable prompts; never calls an AI."""
from __future__ import annotations

import streamlit as st

from advertfloz.application.services.prompt_builder import (
    BriefInputs,
    build_batch_continuation_prompt,
    build_brief_backup,
    build_master_prompt,
    build_output_contract,
    validate_brief,
    what_happens_next,
)
from advertfloz.ui.runtime import get_settings


def render() -> None:
    get_settings()
    st.markdown('<div class="afz-page-title">Marketing Prompt Builder</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="afz-panel">Upload the source repository to your chosen external AI <b>yourself</b>. '
        "AdvertFloz does not receive or scan that repository, and needs no AI API key.</div>",
        unsafe_allow_html=True,
    )

    with st.form("marketing_brief_form"):
        c1, c2 = st.columns(2)
        product_name = c1.text_input("Product / brand name *", placeholder="e.g. MusikFlo")
        product_url = c2.text_input("Website *", placeholder="https://example.com")
        markets = c1.text_input("Target markets *", placeholder="India, Tamil Nadu")
        audiences = c2.text_input("Audience hypotheses", placeholder="Independent music teachers")
        languages = c1.text_input("Output languages", value="English, Tamil")
        tone = c2.text_input("Brand tone", placeholder="Warm, practical")
        start_date = c1.text_input("Campaign start date * (YYYY-MM-DD)", placeholder="2027-01-01")
        duration_choice = c2.selectbox(
            "Campaign duration / planned days",
            [
                "30 days (1-month pilot)",
                "7 days (1-week launch sprint)",
                "14 days (2-week pilot)",
                "60 days (2 months)",
                "90 days (1 quarter)",
                "180 days (6 months)",
                "365 days (Full year)",
            ],
            index=0,
            help="Choose how many days of campaigns to generate. 7, 14, and 30 days are generated in a single response.",
        )
        posting_time = c1.text_input("Posting time", value="09:00")
        timezone = c2.text_input("IANA timezone", value="Asia/Kolkata")
        cadence = c1.text_input("Cadence", value="daily")
        platforms = c2.selectbox("Platforms", ["facebook;instagram", "facebook", "instagram"])
        campaign_tag = c1.text_input("Campaign tag *", placeholder="musikflo_2027")
        outcome = c2.text_input("Primary outcome", placeholder="Sign-ups for the free trial")
        destination_urls = st.text_input("Verified destination URLs (comma-separated)", placeholder="https://example.com/signup")
        features = st.text_area("Known live features", placeholder="verify against uploaded repo")
        claims = st.text_area("Claims to avoid", placeholder="e.g. no revenue guarantees")
        art = st.text_area("Art direction", placeholder="Editorial, calm, high contrast")
        offer_hook = st.text_input("Special offer / conversion hook (optional)", placeholder="e.g. Free instant trial, no credit card required")
        notes = st.text_area("Optional notes", "")
        typo_choice = st.radio(
            "Image typography mode",
            [
                "Direct AI finished posters (All-in-one poster with headline & logo; strict spelling check)",
                "Manual typography overlay (Leave clean open space for Canva / Figma)",
            ],
            index=0,
            help="Choose Direct AI if you have no time for Canva and want ChatGPT to render finished posters with verified spelling.",
        )
        submitted = st.form_submit_button("Validate & build prompt")

    if submitted:
        typo_mode = "manual" if "Manual" in typo_choice else "ai_poster"
        planned_days = int(duration_choice.split()[0])
        brief = BriefInputs(
            product_name=product_name, product_url=product_url, target_markets=markets,
            target_audiences=audiences, languages=languages, brand_tone=tone, campaign_start_date=start_date,
            posting_time=posting_time, timezone=timezone, cadence=cadence, platforms=platforms,
            primary_outcome=outcome, campaign_tag=campaign_tag, destination_urls=destination_urls,
            features_to_verify=features, claims_to_avoid=claims, art_direction=art, other_notes=notes,
            image_typography_mode=typo_mode, planned_days=planned_days, offer_hook=offer_hook,
        )
        st.session_state["marketing_brief_data"] = brief
        result = validate_brief(brief)
        for error in result.errors:
            st.error(error)
        for warning in result.warnings:
            st.warning(warning)
        if result.ok:
            st.success("Brief is valid. Preview and download below.")

    brief: BriefInputs | None = st.session_state.get("marketing_brief_data")
    if brief is None:
        return
    if not validate_brief(brief).ok:
        return

    st.markdown('<div class="afz-section-title">Master Prompt (Copy or Download)</div>', unsafe_allow_html=True)
    st.caption("📋 You can copy the prompt using the copy button on the top-right of the box below, or use the download buttons.")
    with st.expander("Preview & copy master prompt", expanded=True):
        st.code(build_master_prompt(brief), language="text")

    st.markdown('<div class="afz-section-title">Downloads</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.download_button(
        "Download master prompt",
        build_master_prompt(brief),
        file_name="advertfloz_master_prompt.txt",
        mime="text/plain",
    )
    c2.download_button(
        "Download batch/consolidation",
        build_batch_continuation_prompt(),
        file_name="advertfloz_batch_continuation_prompt.txt",
        mime="text/plain",
    )
    c3.download_button(
        "Download output contract",
        build_output_contract(),
        file_name="advertfloz_output_contract.md",
        mime="text/markdown",
    )
    c4.download_button(
        "Download brief (backup)",
        build_brief_backup(brief),
        file_name="advertfloz_brief.md",
        mime="text/markdown",
    )

    st.markdown('<div class="afz-section-title">What happens next?</div>', unsafe_allow_html=True)
    for step in what_happens_next():
        st.write(step)


if __name__ == "__main__":
    render()
