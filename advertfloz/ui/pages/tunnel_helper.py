"""Cloudflare Tunnel Helper (Local Instagram Publishing).

Provides setup guidance, status checking, and configuration assistance for
running a free Cloudflare Quick Tunnel to expose local media assets to Meta's
Instagram Content Publishing API.

Instagram's API requires a publicly accessible HTTPS URL for image uploads.
This page helps operators set up a free Cloudflare tunnel so Meta can reach
images served from the local Streamlit instance.
"""
from __future__ import annotations

import shutil
import subprocess

import streamlit as st

from advertfloz.ui.runtime import get_settings


def render() -> None:
    settings = get_settings()
    st.markdown('<div class="afz-page-title">Cloudflare Tunnel Helper</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="afz-panel">'
        "Instagram's API <b>requires a publicly accessible HTTPS URL</b> for image uploads. "
        "Your laptop's local address (<code>127.0.0.1</code>) is invisible to Meta's servers. "
        "A free Cloudflare Quick Tunnel solves this in one command — no domain, no paid server, no port forwarding."
        "</div>",
        unsafe_allow_html=True,
    )

    # --- Step 1: Check if cloudflared is installed ---
    st.markdown('<div class="afz-section-title">Step 1: Check cloudflared Installation</div>', unsafe_allow_html=True)
    cloudflared_path = shutil.which("cloudflared")

    if cloudflared_path:
        st.success(f"✅ `cloudflared` found at: `{cloudflared_path}`")
        _check_version()
    else:
        st.error("❌ `cloudflared` is NOT installed or not on your PATH.")
        st.markdown(
            "**Install it (pick one):**\n"
            "- **Windows (winget):** `winget install Cloudflare.cloudflared`\n"
            "- **Windows (scoop):** `scoop install cloudflared`\n"
            "- **Manual download:** [github.com/cloudflare/cloudflared/releases](https://github.com/cloudflare/cloudflared/releases/latest)\n"
            "- **macOS (brew):** `brew install cloudflare/cloudflare/cloudflared`\n"
            "- **Linux (apt):** `sudo apt install cloudflared`\n"
        )

    # --- Step 2: How it works ---
    st.markdown('<div class="afz-section-title">Step 2: How the Tunnel Works</div>', unsafe_allow_html=True)
    st.markdown(
        """
**The Problem:** Meta's Instagram API requires `image_url=https://...` — it cannot reach `http://localhost:8501`.

**The Solution:** Cloudflare Quick Tunnel creates a temporary, free, secure HTTPS URL that tunnels to your laptop:

```
Your Laptop (localhost:8501)  ←→  Cloudflare Edge  ←→  Meta's Instagram Bot
                                   https://fast-piano-12.trycloudflare.com
```

**When Meta needs `1.jpg`**, it visits the tunnel URL → Cloudflare routes it to your laptop → your laptop sends the image → Instagram publishes the post!
        """
    )

    # --- Step 3: Start the tunnel ---
    st.markdown('<div class="afz-section-title">Step 3: Start the Tunnel</div>', unsafe_allow_html=True)
    port = st.text_input("Streamlit port", value="8501", help="The port your Streamlit app is running on.")
    tunnel_cmd = f"cloudflared tunnel --url http://localhost:{port}"

    st.markdown("**Run this command in a separate terminal/PowerShell window:**")
    st.code(tunnel_cmd, language="powershell")
    st.caption(
        "Keep this terminal window open while you need the tunnel. "
        "The tunnel URL will appear in the output (e.g., `https://fast-piano-12.trycloudflare.com`)."
    )

    # --- Step 4: Configure AdvertFloz ---
    st.markdown('<div class="afz-section-title">Step 4: Configure AdvertFloz</div>', unsafe_allow_html=True)
    st.markdown(
        "Once you have the tunnel URL, set it in your `.env` file:\n"
    )
    st.code(
        '# In your .env file:\n'
        'ADVERTFLOZ_MEDIA_BASE_URL=https://your-tunnel-id.trycloudflare.com\n'
        '\n'
        '# Example:\n'
        'ADVERTFLOZ_MEDIA_BASE_URL=https://fast-piano-12.trycloudflare.com',
        language="bash",
    )

    current_media_url = getattr(settings, "media_base_url", None) or "(not set)"
    if current_media_url != "(not set)" and current_media_url.startswith("https://"):
        st.success(f"✅ `ADVERTFLOZ_MEDIA_BASE_URL` is configured: `{current_media_url}`")
    else:
        st.warning(
            f"⚠️ Current `ADVERTFLOZ_MEDIA_BASE_URL`: `{current_media_url}` — "
            "Set this to your tunnel URL for Instagram to work."
        )

    # --- Step 5: Verify ---
    st.markdown('<div class="afz-section-title">Step 5: Verify the Tunnel</div>', unsafe_allow_html=True)
    st.markdown(
        "After starting the tunnel and setting the URL, verify it works:\n"
        "1. Open the tunnel URL in your browser (e.g., `https://fast-piano-12.trycloudflare.com`)\n"
        "2. You should see your AdvertFloz app!\n"
        "3. Try accessing an image: `https://your-tunnel.trycloudflare.com/data/media/1.jpg`\n"
    )

    # --- FAQ ---
    st.markdown('<div class="afz-section-title">FAQ</div>', unsafe_allow_html=True)
    with st.expander("Is this free?"):
        st.markdown(
            "**Yes, 100% free.** Cloudflare Quick Tunnels (`trycloudflare.com`) require no account, "
            "no credit card, and no sign-up. They are designed for exactly this use case."
        )
    with st.expander("Is it secure?"):
        st.markdown(
            "The tunnel URL is randomly generated and hard to guess. "
            "It only exposes what's running on your local port. "
            "When you close the terminal, the tunnel immediately stops."
        )
    with st.expander("Does the URL change every time?"):
        st.markdown(
            "**Yes**, Quick Tunnel URLs change each time you restart `cloudflared`. "
            "You'll need to update `ADVERTFLOZ_MEDIA_BASE_URL` in `.env` each time.\n\n"
            "For a **permanent URL**, create a free Cloudflare account and set up a named tunnel. "
            "See: [Cloudflare Tunnel docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)"
        )
    with st.expander("Can I use ngrok instead?"):
        st.markdown(
            "Yes! ngrok works similarly:\n"
            "```\nngrok http 8501\n```\n"
            "However, ngrok's free tier has a session time limit and requires an account. "
            "Cloudflare Quick Tunnels have no such limits."
        )
    with st.expander("What about Facebook (not Instagram)?"):
        st.markdown(
            "**Facebook does NOT need a tunnel.** Facebook's API accepts direct image byte uploads "
            "via `multipart/form-data` — your laptop can upload images directly without a public URL. "
            "The tunnel is only needed for Instagram."
        )


def _check_version() -> None:
    """Display the cloudflared version."""
    try:
        result = subprocess.run(
            ["cloudflared", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            st.caption(f"Version: {result.stdout.strip()}")
        else:
            st.caption("Could not determine version.")
    except Exception:
        st.caption("Could not determine version.")


if __name__ == "__main__":
    render()
