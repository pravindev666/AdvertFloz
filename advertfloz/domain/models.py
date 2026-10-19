"""Domain model dataclasses.

Plain dataclasses mirror the persistence schema (SQLite locally, D1 remotely) so the
same semantics hold in both planes. Frozen where identity must not change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .enums import (
    ActivationState,
    AuthFlow,
    ConnectionState,
    DisclosureStatus,
    ErrorClass,
    IncidentState,
    JobStatus,
    Platform,
    ProductionState,
    Severity,
    SyncState,
)


def _utcnow() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    name: str
    campaign_tag: str
    default_timezone: str
    start_date: str
    end_date: str
    schema_version: str = "1.7"
    created_at: str = field(default_factory=_utcnow)


@dataclass(frozen=True)
class CampaignRevision:
    revision_id: int
    campaign_id: str
    manifest_hash: str
    created_at: str
    created_by: str = "operator"
    notes: str = ""


@dataclass(frozen=True)
class Post:
    """Immutable generation output for a single day; revisions produce new values."""

    post_id: str
    campaign_id: str
    revision_id: int
    image_id: int
    scheduled_at: str          # YYYY-MM-DDTHH:MM:SS local wall time
    timezone: str              # IANA name
    platforms: tuple[Platform, ...]
    caption: str
    facebook_caption: str = ""
    instagram_caption: str = ""
    alt_text: str = ""
    destination_url: str = ""
    grace_minutes: int | None = None
    campaign_tag: str = ""
    ai_disclosure_status: DisclosureStatus = DisclosureStatus.NOT_REVIEWED
    enabled: bool = False
    notes: str = ""

    def effective_caption(self, platform: Platform) -> str:
        platform_caption = {
            Platform.FACEBOOK: self.facebook_caption,
            Platform.INSTAGRAM: self.instagram_caption,
        }[platform]
        return platform_caption.strip() or self.caption


@dataclass
class MediaAsset:
    image_id: int
    filename: str
    sha256: str
    byte_size: int
    mime: str = "image/jpeg"
    width: int = 0
    height: int = 0
    local_path: str = ""
    remote_object_key: str = ""
    production_state: ProductionState = ProductionState.PROMPT_READY
    sync_state: SyncState = SyncState.NOT_SYNCED
    approved: bool = False
    zip_part: str = ""
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)


@dataclass
class PlatformJob:
    post_id: str
    platform: Platform
    campaign_id: str
    revision_id: int
    target_account_id: str
    status: JobStatus = JobStatus.DRAFT
    scheduled_at: str = ""
    timezone: str = ""
    due_at_utc: str = ""
    idempotency_key: str = ""
    attempt_count: int = 0
    next_retry_at: str = ""
    lease_owner: str = ""
    lease_expires_at: str = ""
    remote_post_id: str = ""
    permalink: str = ""
    last_error_class: ErrorClass = ErrorClass.UNKNOWN
    last_stage: str = ""
    container_id: str = ""
    job_id: int = 0
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)


@dataclass
class PublishAttempt:
    post_id: str
    platform: Platform
    stage: str
    correlation_id: str
    attempted_at: str = field(default_factory=_utcnow)
    response_summary: str = ""          # sanitized — never contains tokens/payloads
    error_class: ErrorClass = ErrorClass.UNKNOWN
    retry_decision: str = ""            # retry | no_retry | reconcile


@dataclass
class Connection:
    """OAuth connection metadata. Token ciphertext is stored separately and never displayed."""

    provider: Platform
    auth_flow: AuthFlow = AuthFlow.NONE
    state: ConnectionState = ConnectionState.NOT_CONNECTED
    account_id: str = ""
    account_name: str = ""
    page_id: str = ""
    page_name: str = ""
    scopes: tuple[str, ...] = ()
    issued_at: str = ""
    expires_at: str = ""
    last_validated_at: str = ""
    activation_state: ActivationState = ActivationState.NOT_CONFIGURED
    key_id: str = ""                    # encryption key version used for the stored ciphertext
    updated_at: str = field(default_factory=_utcnow)


@dataclass
class Incident:
    incident_id: str
    severity: Severity
    cause: str
    platform: Platform | None = None
    post_id: str = ""
    diagnosis: str = ""
    remediation: str = ""
    retry_eligible: bool = False
    state: IncidentState = IncidentState.OPEN
    created_at: str = field(default_factory=_utcnow)
    acknowledged_at: str = ""


@dataclass
class AuditEvent:
    actor: str
    action: str
    target: str
    detail: str = ""
    at: str = field(default_factory=_utcnow)


@dataclass
class ImportSession:
    session_id: str
    state: str
    plan_hash: str = ""
    manifest_json: str = ""
    verified_hashes: str = "{}"     # json: image_id -> sha256
    archive_ranges: str = "[]"
    checkpoint: str = ""
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)


@dataclass
class NotificationHealth:
    channel: str = "telegram"
    configured: bool = False
    last_test_at: str = ""
    last_test_ok: bool = False
    last_digest_at: str = ""
    detail: str = ""


@dataclass
class BackupRun:
    backup_id: str
    path: str
    created_at: str = field(default_factory=_utcnow)
    byte_size: int = 0
    includes_secrets: bool = False      # always False for compliant backups
    verified: bool = False
    restore_drill_at: str = ""


@dataclass
class ValidationIssue:
    """A single blocking error or non-blocking warning surfaced to the operator."""

    row: int | None
    field: str
    value: str
    rule: str
    message: str
    severity: Severity = Severity.DANGER

    @property
    def is_blocking(self) -> bool:
        return self.severity in {Severity.DANGER, Severity.CRITICAL}
