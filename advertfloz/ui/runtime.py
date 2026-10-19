"""Shared Streamlit runtime helpers: settings, repository, auth gate, appearance."""
from __future__ import annotations

import streamlit as st

from ..config import Settings, load_settings
from ..infrastructure.persistence.local_sqlite import Repository


@st.cache_resource(show_spinner=False)
def _repo_for(path: str) -> Repository:
    return Repository(path)


def get_settings() -> Settings:
    settings = st.session_state.get("settings")
    if not isinstance(settings, Settings) or not hasattr(settings, "admin_password_configured"):
        settings = load_settings()
        st.session_state["settings"] = settings
    return settings


def get_repo() -> Repository:
    settings = get_settings()
    return _repo_for(str(settings.db_path))


def is_dark() -> bool:
    return bool(st.session_state.get("afz_dark", False))


def appearance_toggle() -> None:
    st.session_state["afz_dark"] = st.toggle(
        "Dark appearance", value=is_dark(), help="Switch between the light and dark brand themes."
    )


import hmac


def hosted_auth_ok() -> bool:
    """Fail closed: a hosted control plane without auth is unusable."""
    settings = get_settings()
    if not getattr(settings, "hosted", False):
        return True
    if not hasattr(settings, "hosted_auth_ready") or not settings.hosted_auth_ready():
        return False
    # Check Cloudflare Access Zero Trust header if present
    try:
        headers = getattr(st.context, "headers", {})
        cf_email = (headers.get("cf-access-authenticated-user-email") or headers.get("Cf-Access-Authenticated-User-Email") or "").lower().strip()
        if cf_email and getattr(settings, "operator_allowlist", ()):
            if cf_email in {a.lower() for a in settings.operator_allowlist}:
                st.session_state["afz_user_email"] = cf_email
                st.session_state["afz_authenticated"] = True
                return True
    except Exception:
        pass

    claims = st.session_state.get("oidc_claims")
    if not claims:
        return False
    email = (claims.get("email") or claims.get("preferred_username") or "").lower()
    return email in {a.lower() for a in getattr(settings, "operator_allowlist", ())}


def enforce_hosted_gate() -> bool:
    """Return True when the current session may use the control plane."""
    settings = get_settings()

    # 1. Master Password Gate (works locally or in hosted mode)
    if getattr(settings, "admin_password_configured", False):
        if st.session_state.get("afz_authenticated", False):
            return True

        # Render sleek login card
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown('<div class="afz-wordmark" style="font-size:2.2rem;margin-top:2rem;margin-bottom:0.25rem;">◧ AdvertFloz</div>', unsafe_allow_html=True)
            st.markdown("### 🔒 Operator Authentication")
            st.caption("This AdvertFloz dashboard is private. Enter your master access key to unlock the campaign command center.")
            with st.form("afz_login_form"):
                pwd_input = st.text_input("Master Access Key / Password", type="password", placeholder="Enter your secret key...")
                submitted = st.form_submit_button("Unlock Command Center", type="primary", use_container_width=True)
                if submitted:
                    expected = settings.secret("ADVERTFLOZ_ADMIN_PASSWORD")
                    if pwd_input and expected and hmac.compare_digest(pwd_input.strip(), expected.strip()):
                        st.session_state["afz_authenticated"] = True
                        st.rerun()
                    else:
                        st.error("Invalid access key. Access denied.")
            st.info("💡 **Protected by AdvertFloz Zero-Trust Gate.** Set `ADVERTFLOZ_ADMIN_PASSWORD` in your `.env` or Streamlit secrets to manage this key.")
        return False

    # 2. Hosted OIDC / Cloudflare Zero Trust Gate
    if not settings.hosted:
        return True
    if not settings.hosted_auth_ready():
        st.error(
            "This hosted control panel is not configured with authentication. "
            "Set ADVERTFLOZ_ADMIN_PASSWORD or ADVERTFLOZ_OIDC_ISSUER + ADVERTFLOZ_OPERATOR_ALLOWLIST. Failing closed."
        )
        return False
    if not hosted_auth_ok():
        st.error("You are not on the configured operator allowlist. Access denied.")
        return False
    return True


def first_run_complete() -> bool:
    repo = get_repo()
    return repo.get_flag("first_run_complete") == "1"


def mark_first_run_complete() -> None:
    repo = get_repo()
    repo.set_flag("first_run_complete", "1")
