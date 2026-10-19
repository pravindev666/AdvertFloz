"""AdvertFloz Streamlit entry point.

Run from the repository root:  ``streamlit run streamlit_app.py``

Streamlit is the control plane, never the scheduler of record. Scheduling is performed by the
bounded local scheduler (``python -m advertfloz.scheduler_cli tick``) or the remote Worker.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the repository root is importable regardless of how Streamlit resolves the script.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from advertfloz.ui.navigation import run  # noqa: E402

run()
