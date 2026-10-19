"""R2 (Cloudflare) media client.

Remote media storage is only used after the zero-cost gate passes. Without configured
credentials this client reports a precise blocker instead of faking an upload.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class R2Config:
    account_id: str = ""
    bucket: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    worker_base_url: str = ""
    signed_url_ttl_seconds: int = 900

    @property
    def configured(self) -> bool:
        return bool(self.account_id and self.bucket and ((self.access_key_id and self.secret_access_key) or self.worker_base_url))


class R2NotConfigured(RuntimeError):
    pass


class R2Client:
    """Uploads private media and returns short-lived signed URLs.

    Real R2 S3-compatible calls are performed by the deployed Worker (which holds the
    credentials). The Python control plane talks to the Worker, never to R2 directly, so no
    R2 secret is needed in the control plane.
    """

    def __init__(self, config: R2Config):
        self.config = config

    def upload(self, local_path: str | Path, image_id: int) -> str:
        if not self.config.configured:
            raise R2NotConfigured(
                "R2 is not configured. Remote media upload requires the zero-cost gate to pass "
                "and Worker credentials (WORKER_BASE_URL + WORKER_SERVICE_KEY)."
            )
        raise R2NotConfigured("Remote upload path is exercised by the Worker; not available in this process.")

    def signed_url(self, object_key: str) -> str:
        if not self.config.configured:
            raise R2NotConfigured("R2 is not configured; cannot produce a signed media URL.")
        return f"{self.config.worker_base_url}/media/{object_key}?ttl={self.config.signed_url_ttl_seconds}"
