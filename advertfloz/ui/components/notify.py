"""Persistent notification area and local-mode banner (PRD §4.1)."""
from __future__ import annotations

from ...application.services.notifications import digest_is_stale
from ...domain.enums import IncidentState


def local_mode_banner(st, mode: str) -> None:
    if mode == "local":
        st.markdown(
            '<div class="afz-local-banner" role="status">'
            "Local mode: publishing stops while this machine, the app or the scheduler process is off or asleep. "
            "Remote mode requires the zero-cost gate to pass.</div>",
            unsafe_allow_html=True,
        )


def notification_area(st, repo, mode: str) -> None:
    """Blocking issues, unresolved UNKNOWN_OUTCOME and required reauthorization."""
    messages: list[tuple[str, str]] = []

    unknown = repo.unknown_outcome_count()
    if unknown:
        messages.append(("error", f"{unknown} job(s) have an UNKNOWN_OUTCOME. Reconcile with the provider before any retry."))

    for incident in repo.list_incidents(IncidentState.OPEN):
        if incident.cause in {"authorization", "account_restriction", "stale_worker"}:
            messages.append(("error", f"[{incident.cause}] {incident.diagnosis}"))

    if repo.get_flag("pause_all") == "1":
        messages.append(("warning", "All-platform emergency pause is active. New dispatches are blocked."))

    if digest_is_stale(repo):
        messages.append(("warning", "The daily health digest is missing or stale."))

    if mode == "remote" and repo.get_flag("worker_heartbeat_at") == "":
        messages.append(("warning", "No remote worker heartbeat recorded yet."))

    if not messages:
        return
    with st.expander(f"Notifications ({len(messages)})", expanded=any(level == "error" for level, _ in messages)):
        for level, text in messages:
            (st.error if level == "error" else st.warning)(text)
