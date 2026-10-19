"""Zero-cost deployment gate (FR-030).

    python scripts/cost_gate.py

Remote mode stays NO-GO until every prerequisite passes on the real account. Failing the gate
keeps local mode working and never enables a paid fallback.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from advertfloz.config import load_settings  # noqa: E402
from advertfloz.diagnostics import run_cost_gate  # noqa: E402


def main() -> int:
    settings = load_settings()
    gate = run_cost_gate(settings)
    print(f"Decision: {'GO' if gate.allowed else 'NO-GO'} ({gate.decided_at})")
    print(f"Reason: {gate.reason}\n")
    for check in gate.checks:
        print(f"[{check.status.value:7}] {check.name:24} {check.detail}")
    return 0 if gate.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
