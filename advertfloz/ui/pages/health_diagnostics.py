"""Integration Health & Diagnostics.

Provides real-time, authenticated verification of Cloudflare D1, Cloudflare R2,
and Meta Graph API without exposing tokens or internal credentials.
"""
from __future__ import annotations

import streamlit as st

from advertfloz.infrastructure.integration_verifier import run_all_integration_checks
from advertfloz.ui.components.status import chip
from advertfloz.ui.runtime import get_repo, get_settings


def render() -> None:
    settings = get_settings()
    repo = get_repo()

    st.markdown('<div class="afz-page-title">🛡️ System Integration Health</div>', unsafe_allow_html=True)
    st.caption(
        "Live diagnostic verification of Cloudflare D1 database, Cloudflare R2 media storage, "
        "and Meta publishing permissions. Real requests are executed; zero mock status."
    )

    col_btn, col_info = st.columns([1.5, 4])
    with col_btn:
        run_check = st.button("🔄 Check Integrations Now", type="primary", use_container_width=True)

    if run_check or "diag_results" not in st.session_state:
        with st.spinner("Executing real integration diagnostic cycles…"):
            st.session_state["diag_results"] = run_all_integration_checks(settings, repo)

    results = st.session_state.get("diag_results", [])

    st.markdown("---")

    # Render each integration card
    for res in results:
        status_tone = (
            "success" if res.status == "Healthy"
            else ("warning" if res.status in {"Degraded", "Not Configured"} else "danger")
        )

        with st.container():
            st.markdown(
                f"""
                <div class="afz-panel">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span style="font-size:1.15rem; font-weight:600;">{res.service}</span>
                        <span>{chip(res.status, status_tone)}</span>
                    </div>
                    <div style="font-size:0.95rem; margin-bottom:8px;">{res.detail}</div>
                    <div style="display:flex; gap:16px; font-size:0.85rem; color:var(--afz-text-alt);">
                        <span>⏱️ Latency: <b>{res.latency_ms} ms</b></span>
                        <span>🕒 Last Checked: <b>{res.checked_at}</b></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if res.status != "Healthy":
                st.warning(f"**Recommended Action**: {res.recommendation}")

    st.markdown("---")
    st.markdown("### 📋 Environment & Service Configuration")

    mode_lbl = settings.mode.title()
    worker_status = "Configured" if settings.worker_configured else "Not Configured"
    meta_status = "Configured" if settings.meta_app_configured else "Not Configured"

    ec1, ec2, ec3, ec4 = st.columns(4)
    ec1.metric("Execution Mode", mode_lbl)
    ec2.metric("Worker API", worker_status)
    ec3.metric("Meta App", meta_status)
    ec4.metric("Timezone", settings.default_timezone)


if __name__ == "__main__":
    render()
