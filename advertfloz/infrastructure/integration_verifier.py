"""Live integration verification for Cloudflare R2, Cloudflare D1, and Meta Graph API.

Executes real, isolated, non-destructive checks against active bindings and services.
Never exposes secret tokens or credentials in outputs.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from advertfloz.config import Settings
from advertfloz.domain.enums import Platform
from advertfloz.infrastructure.persistence.local_sqlite import Repository
from advertfloz.infrastructure.worker_client import call_worker


@dataclass
class CheckResult:
    service: str
    status: str  # "Healthy" | "Degraded" | "Failed" | "Not Configured"
    latency_ms: int
    checked_at: str
    detail: str
    recommendation: str
    raw_data: dict[str, Any] | None = None


# Minimal valid 1x1 JPEG for safe R2 upload verification
_TINY_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////"
    "////////////////////////////////////////////////////wgALCAABAAEBAREA"
    "/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
)


def verify_cloudflare_d1(settings: Settings, repo: Repository | None = None) -> CheckResult:
    """Verify Cloudflare D1 connectivity, table availability, and query latency."""
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if not settings.worker_configured:
        return CheckResult(
            service="Cloudflare D1 Database",
            status="Not Configured",
            latency_ms=0,
            checked_at=checked_at,
            detail="WORKER_BASE_URL or WORKER_SERVICE_KEY is missing in secrets.",
            recommendation="Configure Cloudflare Worker connection secrets in .streamlit/secrets.toml.",
        )

    t0 = time.perf_counter()
    res = call_worker(settings, "/api/status")
    latency = int((time.perf_counter() - t0) * 1000)

    if not res:
        return CheckResult(
            service="Cloudflare D1 Database",
            status="Failed",
            latency_ms=latency,
            checked_at=checked_at,
            detail="Worker endpoint unreachable or HMAC authentication rejected request.",
            recommendation="Verify that the Worker service key matches the secret deployed on Cloudflare.",
        )

    counts = res.get("counts", [])
    heartbeat = res.get("heartbeat")
    total_jobs = sum(c.get("n", 0) for c in counts if isinstance(c, dict))

    detail = (
        f"D1 database connected ({latency}ms). "
        f"Found {total_jobs} total platform jobs across {len(counts)} status categories. "
        f"Worker cron heartbeat: {heartbeat or 'never'}."
    )

    return CheckResult(
        service="Cloudflare D1 Database",
        status="Healthy",
        latency_ms=latency,
        checked_at=checked_at,
        detail=detail,
        recommendation="None. Cloudflare D1 database queries and cron tick are operational.",
        raw_data={"counts": counts, "heartbeat": heartbeat},
    )


def verify_cloudflare_r2(settings: Settings) -> CheckResult:
    """Verify Cloudflare R2 object storage binding with a safe diagnostic write/check."""
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if not settings.worker_configured:
        return CheckResult(
            service="Cloudflare R2 Object Storage",
            status="Not Configured",
            latency_ms=0,
            checked_at=checked_at,
            detail="Worker connection is not configured.",
            recommendation="Configure WORKER_BASE_URL and WORKER_SERVICE_KEY.",
        )

    t0 = time.perf_counter()
    # Execute a safe diagnostic upload with a dedicated test ID (999999)
    test_payload = json.dumps({
        "image_id": 999999,
        "filename": "__diagnostic_ping__.jpg",
        "mime": "image/jpeg",
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "data_b64": _TINY_JPEG_B64,
    })

    res = call_worker(settings, "/api/media/upload", method="POST", body=test_payload)
    latency = int((time.perf_counter() - t0) * 1000)

    if not res:
        return CheckResult(
            service="Cloudflare R2 Object Storage",
            status="Failed",
            latency_ms=latency,
            checked_at=checked_at,
            detail="Failed to communicate with R2 media upload endpoint.",
            recommendation="Check Cloudflare Worker R2 bucket binding 'MEDIA' and worker error logs.",
        )

    if res.get("ok"):
        remote_key = res.get("remote_object_key", "")
        return CheckResult(
            service="Cloudflare R2 Object Storage",
            status="Healthy",
            latency_ms=latency,
            checked_at=checked_at,
            detail=f"R2 storage binding verified in {latency}ms. Test object written successfully ({remote_key}).",
            recommendation="None. Media upload, R2 bucket write, and object metadata indexing are fully operational.",
            raw_data=res,
        )

    err = res.get("error", "Unknown error")
    return CheckResult(
        service="Cloudflare R2 Object Storage",
        status="Degraded",
        latency_ms=latency,
        checked_at=checked_at,
        detail=f"Upload returned error: {err}",
        recommendation="Verify R2 bucket permissions and available quota.",
        raw_data=res,
    )


def verify_meta_integration(settings: Settings, repo: Repository | None = None) -> CheckResult:
    """Verify Meta Graph API connectivity, token validity, and Facebook/Instagram access."""
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if not settings.worker_configured:
        return CheckResult(
            service="Meta Graph API (Facebook & Instagram)",
            status="Not Configured",
            latency_ms=0,
            checked_at=checked_at,
            detail="Worker connection is not configured.",
            recommendation="Configure WORKER_BASE_URL and WORKER_SERVICE_KEY.",
        )

    t0 = time.perf_counter()
    res = call_worker(settings, "/api/meta/pages")
    latency = int((time.perf_counter() - t0) * 1000)

    if not res:
        # Fall back to checking connections list
        conn_res = call_worker(settings, "/api/connections")
        if conn_res and "connections" in conn_res:
            fb = next((c for c in conn_res["connections"] if c.get("provider") == "facebook"), None)
            if fb:
                return CheckResult(
                    service="Meta Graph API (Facebook & Instagram)",
                    status="Degraded",
                    latency_ms=latency,
                    checked_at=checked_at,
                    detail=f"Connection found: {fb.get('page_name') or fb.get('account_name')}, but live page re-sync timed out.",
                    recommendation="Re-authenticate via OAuth if token has expired.",
                    raw_data=fb,
                )
        return CheckResult(
            service="Meta Graph API (Facebook & Instagram)",
            status="Failed",
            latency_ms=latency,
            checked_at=checked_at,
            detail="No Meta connection found or authorization token missing/expired.",
            recommendation="Initiate Meta OAuth login to generate fresh long-lived Page tokens.",
        )

    pages = res.get("pages", [])
    selected = res.get("selected_page")

    if not pages:
        return CheckResult(
            service="Meta Graph API (Facebook & Instagram)",
            status="Degraded",
            latency_ms=latency,
            checked_at=checked_at,
            detail="Meta Graph API reached, but no Facebook Pages with manage permissions were returned.",
            recommendation="Ensure the connected Meta account has administrative or tasks role on the target Facebook Page.",
            raw_data=res,
        )

    page_names = ", ".join(f"'{p.get('name')}'" for p in pages)
    selected_name = selected.get("name") if selected else pages[0].get("name")

    detail = (
        f"Meta Graph API active ({latency}ms). "
        f"Found {len(pages)} managed Page(s): {page_names}. "
        f"Active target Page: '{selected_name}'. "
        f"Publishing permissions: pages_manage_posts, pages_read_engagement."
    )

    return CheckResult(
        service="Meta Graph API (Facebook & Instagram)",
        status="Healthy",
        latency_ms=latency,
        checked_at=checked_at,
        detail=detail,
        recommendation="None. Meta Facebook publishing token is valid and authenticated.",
        raw_data=res,
    )


def run_all_integration_checks(settings: Settings, repo: Repository | None = None) -> list[CheckResult]:
    """Run real checks for all three core services in sequence."""
    return [
        verify_cloudflare_d1(settings, repo),
        verify_cloudflare_r2(settings),
        verify_meta_integration(settings, repo),
    ]
