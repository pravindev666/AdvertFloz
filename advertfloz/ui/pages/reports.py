"""Reports & Export (FR-027, PRD §4.13)."""
from __future__ import annotations

import streamlit as st

from advertfloz.application.services import reporting
from advertfloz.ui.runtime import get_repo


def render() -> None:
    repo = get_repo()
    st.markdown('<div class="afz-page-title">Reports &amp; Export</div>', unsafe_allow_html=True)

    if not repo.count_jobs_by_status():
        st.info("No published or queued outcomes yet. Reports become useful after activation and dispatch.")
        # Still show Meta Suite export and Auto-ZIP even without jobs
        _meta_suite_section(repo)
        _auto_zip_section()
        return

    st.markdown('<div class="afz-section-title">what_actually_posted.csv</div>', unsafe_allow_html=True)
    st.caption("One row per platform outcome: post ID, platform, scheduled/actual time, status, remote ID/permalink, "
               "campaign tag, destination and error category.")
    st.download_button("Download what_actually_posted.csv",
                       reporting.what_actually_posted_csv(repo), file_name="what_actually_posted.csv")

    c1, c2, c3 = st.columns(3)
    c1.download_button("Failed jobs", reporting.failed_jobs_csv(repo), file_name="failed_jobs.csv")
    c2.download_button("Unknown outcome jobs", reporting.unknown_jobs_csv(repo), file_name="unknown_outcome_jobs.csv")
    c3.download_button("Missed jobs", reporting.missed_jobs_csv(repo), file_name="missed_jobs.csv")

    st.download_button("Audit history", reporting.audit_csv(repo), file_name="audit_events.csv")

    st.markdown('<div class="afz-section-title">UTM export</div>', unsafe_allow_html=True)
    campaigns = repo.list_campaigns()
    if campaigns:
        campaign = st.selectbox("Campaign", campaigns, format_func=lambda c: c.name)
        revision = repo.latest_revision(campaign.campaign_id)
        if revision is not None:
            st.download_button("Download utm_urls.csv",
                               reporting.utm_export_csv(repo, campaign.campaign_id, revision.revision_id),
                               file_name="utm_urls.csv")
            counts = reporting.per_platform_success_counts(repo)
            st.caption(f"Published so far — Facebook {counts['facebook']}, Instagram {counts['instagram']}")

    _meta_suite_section(repo)
    _auto_zip_section()

    st.caption("Measured impressions/reach/clicks are shown only when imported from a real supported source; "
               "AdvertFloz never invents them.")


def _meta_suite_section(repo) -> None:
    """Meta Business Suite Planner CSV fallback export."""
    st.markdown('<div class="afz-section-title">Meta Business Suite Planner Export (Fallback)</div>', unsafe_allow_html=True)
    st.caption(
        "🛟 **Zero-downtime fallback:** If you have Meta API credential issues or App Review delays, "
        "download this CSV and upload it directly to "
        "[Meta Business Suite Planner](https://business.facebook.com/latest/content_calendar) "
        "for manual scheduling. No API keys required."
    )
    campaigns = repo.list_campaigns()
    if campaigns:
        campaign = st.selectbox(
            "Campaign (for Meta Suite export)",
            campaigns,
            format_func=lambda c: f"{c.name} ({c.campaign_id})",
            key="meta_suite_campaign",
        )
        revision = repo.latest_revision(campaign.campaign_id)
        if revision is not None:
            st.download_button(
                "📥 Export for Meta Business Suite Planner",
                reporting.meta_business_suite_csv(repo, campaign.campaign_id, revision.revision_id),
                file_name="meta_business_suite_schedule.csv",
                mime="text/csv",
                type="primary",
            )
        else:
            st.info("No revision found for this campaign.")
    else:
        st.info("No campaign imported yet. Import a campaign first, then export here.")


def _auto_zip_section() -> None:
    """Auto-ZIP creator helper info."""
    st.markdown('<div class="afz-section-title">Auto-ZIP Batch Creator</div>', unsafe_allow_html=True)
    st.caption(
        "📦 Use the built-in Auto-ZIP tool to validate and package your AI-generated images "
        "into the correct flat ZIP format for import."
    )
    with st.expander("How to use the Auto-ZIP tool"):
        st.code(
            'python -m advertfloz.tools.make_zip --folder ./my_images\n'
            '\n'
            '# Or specify a range:\n'
            'python -m advertfloz.tools.make_zip --folder ./my_images --range 1-30\n'
            '\n'
            '# Or specify output path:\n'
            'python -m advertfloz.tools.make_zip -f ./my_images -o campaign_images.zip',
            language="powershell",
        )
        st.markdown(
            "**What it does:**\n"
            "- ✅ Verifies every image is a valid JPEG (checks SOI header)\n"
            "- ✅ Checks sequential naming (`1.jpg`, `2.jpg`, ... `N.jpg`)\n"
            "- ✅ Warns if any images are missing from the sequence\n"
            "- ✅ Enforces 10 MB per-image and 50 MB total limits\n"
            "- ✅ Creates a **flat ZIP** (no subfolder nesting mistakes)\n"
        )


if __name__ == "__main__":
    render()

