"""Interactive Guided Tutorial Callout Component."""
from __future__ import annotations

import streamlit as st

TUTORIAL_STEPS = [
    {
        "step": 1,
        "title": "Upload CSV Plan & Images ZIP",
        "page": "Campaign Import",
        "icon": "📁",
        "tagline": "How to load your post schedule and graphics into AdvertFloz",
        "instructions": [
            "**Go to 'Campaign Import'** on the left sidebar.",
            "Upload your **CSV file** (contains schedule dates, times, captions, and platforms).",
            "Upload your **.zip file** containing your images (e.g. `1.jpg`, `2.jpg`, etc.).",
            "Click **'Proceed to Step 5 · Review & Commit'**, then click **'🚀 Commit Campaign Revision'**.",
        ],
        "tip": "💡 Your posts are now saved as drafts with exact scheduled times in your Calendar!",
    },
    {
        "step": 2,
        "title": "Select Target Facebook Page",
        "page": "Facebook Page",
        "icon": "🎯",
        "tagline": "Choose which Facebook Page your posts will publish to",
        "instructions": [
            "**Go to 'Facebook Page'** on the left sidebar.",
            "Confirm the green banner says: `Connected Facebook Page: MusikFlo` (or your active page).",
            "In the **'Target Facebook Page' dropdown**, pick **MusikFlo** or **Rashinos**.",
            "Click **'Switch Target Page'** if you want to change the target.",
        ],
        "tip": "💡 Any page you pick here is where all your future scheduled posts will publish!",
    },
    {
        "step": 3,
        "title": "Queue Posts & Push to Cloudflare Worker",
        "page": "Publishing Queue",
        "icon": "🚀",
        "tagline": "Arm Cloudflare Worker to publish your posts on autopilot",
        "instructions": [
            "**Go to 'Publishing Queue'** on the left sidebar.",
            "Look for the blue card: **'🚀 Push Campaign & Schedule to Facebook'**.",
            "Click **'Queue Posts & Push to Cloudflare Worker'**.",
            "AdvertFloz automatically uploads all your images to Cloudflare R2 and syncs the schedule to Cloudflare D1.",
        ],
        "tip": "💡 Once queued, your browser doesn't even need to be open — Cloudflare handles it 24/7!",
    },
    {
        "step": 4,
        "title": "Watch It Publish (Today, Tomorrow & Everyday)",
        "page": "Publishing Queue",
        "icon": "⚡",
        "tagline": "Automatic cron publishing & instant test",
        "instructions": [
            "Cloudflare's background cron runs **every 5 minutes** automatically.",
            "When a post's scheduled time arrives (e.g., today at 9:00 AM), Cloudflare posts it to Facebook.",
            "**Want to see it on Facebook right now?** Click **'⚡ Publish Due Post Now'** on the Publishing Queue page to post the first due image immediately!",
            "Tomorrow at 9:00 AM, Cloudflare Worker automatically publishes Post 2, the next day Post 3, and so on!",
        ],
        "tip": "💡 Check 'Calendar' to see all your upcoming posts mapped out across the month!",
    },
]


def render_tutorial_callout(current_page_name: str | None = None) -> None:
    """Render an interactive, collapsible tutorial banner with skip/next controls."""
    if st.session_state.get("tutorial_dismissed", False):
        with st.sidebar:
            if st.button("📖 Open Guided Tutorial", help="Open the step-by-step guided tutorial", key="reopen_tutorial"):
                st.session_state["tutorial_dismissed"] = False
                st.rerun()
        return

    current_idx = st.session_state.get("tutorial_step_idx", 0)
    current_idx = max(0, min(current_idx, len(TUTORIAL_STEPS) - 1))
    step_data = TUTORIAL_STEPS[current_idx]

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, rgba(79, 70, 229, 0.08) 0%, rgba(15, 118, 110, 0.08) 100%);
            border: 1px solid rgba(79, 70, 229, 0.3);
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 16px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-weight: 700; font-size: 1.05rem; color: #4F46E5;">
                    {step_data['icon']} Step {step_data['step']} of 4: {step_data['title']}
                </span>
                <span style="font-size: 0.82rem; color: #475569; background: rgba(0,0,0,0.06); padding: 3px 10px; border-radius: 20px;">
                    Page: <b>{step_data['page']}</b>
                </span>
            </div>
            <p style="margin: 0; font-size: 0.92rem; color: #475569;">
                {step_data['tagline']}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        for instruction in step_data["instructions"]:
            st.markdown(f"- {instruction}")
        st.info(step_data["tip"])

        c_prev, c_next, c_skip = st.columns([1, 1, 2])
        if current_idx > 0:
            if c_prev.button("⬅ Previous", key=f"tut_prev_{current_idx}"):
                st.session_state["tutorial_step_idx"] = current_idx - 1
                st.rerun()

        if current_idx < len(TUTORIAL_STEPS) - 1:
            if c_next.button("Next Step ➔", type="primary", key=f"tut_next_{current_idx}"):
                st.session_state["tutorial_step_idx"] = current_idx + 1
                st.rerun()
        else:
            if c_next.button("Finish Tutorial 🎉", type="primary", key=f"tut_finish_{current_idx}"):
                st.session_state["tutorial_dismissed"] = True
                st.rerun()

        if c_skip.button("✕ Dismiss / Skip Tutorial", key=f"tut_skip_{current_idx}", help="Hide tutorial (re-open anytime from sidebar)"):
            st.session_state["tutorial_dismissed"] = True
            st.rerun()

    st.markdown("<hr style='margin: 15px 0 25px 0; border: none; border-top: 1px dashed rgba(0,0,0,0.12);'>", unsafe_allow_html=True)
