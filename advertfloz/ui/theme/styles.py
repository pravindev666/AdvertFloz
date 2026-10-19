"""Theme application for Streamlit.

Base colors come from ``.streamlit/config.toml`` (the supported mechanism). This module adds
semantic CSS variables and a small, stable set of component styles for our own HTML fragments.
It deliberately avoids Streamlit's generated class names.
"""
from __future__ import annotations

from .tokens import get_tokens


def css_variables(dark: bool = False) -> str:
    t = get_tokens(dark)
    lines = [f"  --afz-{name.replace('_', '-')}: {value};" for name, value in t.items()]
    return ":root {\n" + "\n".join(lines) + "\n}"


def apply_theme(st, dark: bool = False) -> None:
    """Inject semantic variables and minimal component styles.

    ``st`` is the Streamlit module, passed in to keep this import-free of Streamlit so tests
    can call ``css_variables`` directly.
    """
    css = f"""
    <style>
    {css_variables(dark)}
    .afz-badge,
    .afz-chip {{
        display: inline-flex; align-items: center; gap: 6px;
        padding: 2px 8px; border-radius: 10px; font-size: 13px;
        border: 1px solid var(--afz-border); background: var(--afz-surface-alt);
        color: var(--afz-text); line-height: 1.6;
    }}
    .afz-tone-success {{ background: var(--afz-success-surface); color: var(--afz-success); border-color: var(--afz-success); }}
    .afz-tone-warning {{ background: var(--afz-warning-surface); color: var(--afz-warning); border-color: var(--afz-warning); }}
    .afz-tone-danger  {{ background: var(--afz-danger-surface);  color: var(--afz-danger);  border-color: var(--afz-danger); }}
    .afz-tone-info    {{ background: var(--afz-info-surface);    color: var(--afz-info);    border-color: var(--afz-info); }}
    .afz-tone-neutral {{ background: var(--afz-surface-alt);     color: var(--afz-text-alt); border-color: var(--afz-border); }}
    .afz-mono {{
        font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
        background: var(--afz-mono-bg); padding: 1px 6px; border-radius: 6px; font-size: 13px;
    }}
    .afz-panel {{
        border: 1px solid var(--afz-border); border-radius: 12px; background: var(--afz-surface);
        padding: 16px; margin-bottom: 12px;
    }}
    .afz-local-banner {{
        border: 1px solid var(--afz-warning); background: var(--afz-warning-surface);
        color: var(--afz-warning); border-radius: 10px; padding: 8px 12px; font-size: 13px;
        margin-bottom: 10px;
    }}
    .afz-wordmark {{ font-size: 20px; font-weight: 700; color: var(--afz-primary); letter-spacing: 0.2px; }}
    .afz-summary-label {{ color: var(--afz-text-alt); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    .afz-summary-value {{ color: var(--afz-text); font-size: 16px; font-weight: 600; }}
    .afz-page-title {{ font-size: 28px; font-weight: 700; color: var(--afz-text); margin: 0 0 4px 0; }}
    .afz-section-title {{ font-size: 20px; font-weight: 600; color: var(--afz-text); margin: 12px 0 6px 0; }}
    .afz-muted {{ color: var(--afz-text-alt); font-size: 14px; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
