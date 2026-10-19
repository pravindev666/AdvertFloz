"""Domain enums — the canonical status vocabulary for AdvertFloz v1.7.

These names are part of the product contract (PRD §9). Do not rename values without
updating every consumer, the D1 schema, exporters and tests together.
"""
from __future__ import annotations

from enum import Enum


class Platform(str, Enum):
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"

    @property
    def label(self) -> str:
        return {"facebook": "Facebook", "instagram": "Instagram"}[self.value]


class JobStatus(str, Enum):
    """Per post × platform × campaign_revision lifecycle state."""

    DRAFT = "DRAFT"
    VALIDATION_BLOCKED = "VALIDATION_BLOCKED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    SYNC_PENDING = "SYNC_PENDING"
    SYNCED = "SYNCED"
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    PROCESSING_MEDIA = "PROCESSING_MEDIA"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    MISSED = "MISSED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in {
            JobStatus.PUBLISHED,
            JobStatus.FAILED_PERMANENT,
            JobStatus.MISSED,
            JobStatus.CANCELLED,
        }

    @property
    def is_in_flight(self) -> bool:
        """Claimed or actively being processed — never edited blindly, reconcile first."""
        return self in {JobStatus.CLAIMED, JobStatus.PROCESSING_MEDIA, JobStatus.PUBLISHING}

    @property
    def allows_manual_retry(self) -> bool:
        """Only classified-retryable failures may be retried directly."""
        return self is JobStatus.FAILED_RETRYABLE

    @property
    def requires_reconciliation(self) -> bool:
        """Ambiguous outcomes must be reconciled with the provider before any retry."""
        return self is JobStatus.UNKNOWN_OUTCOME

    @property
    def is_published(self) -> bool:
        return self is JobStatus.PUBLISHED


class ProductionState(str, Enum):
    """Human image-production trail (UI §Image Production)."""

    PROMPT_READY = "prompt_ready"
    GENERATED = "generated"
    OVERLAY_DONE = "overlay_done"
    APPROVED = "approved"
    NAMED = "named"
    INCLUDED_IN_ZIP = "included_in_zip"
    UPLOADED = "uploaded"
    SYNCED = "synced"
    READY = "ready"

    @property
    def order(self) -> int:
        return _PRODUCTION_ORDER[self]


_PRODUCTION_ORDER = {
    ProductionState.PROMPT_READY: 0,
    ProductionState.GENERATED: 1,
    ProductionState.OVERLAY_DONE: 2,
    ProductionState.APPROVED: 3,
    ProductionState.NAMED: 4,
    ProductionState.INCLUDED_IN_ZIP: 5,
    ProductionState.UPLOADED: 6,
    ProductionState.SYNCED: 7,
    ProductionState.READY: 8,
}

#: Manual states an operator sets; the rest are verified automatically.
MANUAL_PRODUCTION_STATES = frozenset(
    {ProductionState.GENERATED, ProductionState.OVERLAY_DONE, ProductionState.APPROVED}
)
AUTO_PRODUCTION_STATES = frozenset(
    {
        ProductionState.NAMED,
        ProductionState.INCLUDED_IN_ZIP,
        ProductionState.UPLOADED,
        ProductionState.SYNCED,
    }
)


class ActivationState(str, Enum):
    """Per-platform readiness gate (UI §First-run wizard F)."""

    NOT_CONFIGURED = "Not configured"
    NEEDS_OPERATOR_ACTION = "Needs operator action"
    READY_FOR_LOCAL_PILOT = "Ready for local pilot"
    READY_FOR_REMOTE_CANARY = "Ready for remote canary"
    ACTIVE = "Active"
    PAUSED = "Paused"
    BLOCKED = "Blocked"


class DisclosureStatus(str, Enum):
    NOT_REVIEWED = "not_reviewed"
    NOT_REQUIRED = "not_required"
    REQUIRED_PENDING = "required_pending"
    COMPLETED = "completed"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    DANGER = "danger"
    CRITICAL = "critical"


class IncidentState(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class ConnectionState(str, Enum):
    """OAuth connection lifecycle. Distinct from 'can publish'."""

    NOT_CONNECTED = "not_connected"
    AUTHORIZATION_PENDING = "authorization_pending"
    CONNECTED_NO_TARGET = "connected_no_target"
    TARGET_SELECTED = "target_selected"
    PERMISSION_MISSING = "permission_missing"
    TEST_PASSED = "test_passed"
    RECONNECT_REQUIRED = "reconnect_required"
    RESTRICTED = "restricted"
    DISCONNECTED = "disconnected"


class AuthFlow(str, Enum):
    """Configured Meta authorization flow."""

    FACEBOOK_LOGIN = "facebook_login"           # linked IG professional account
    INSTAGRAM_LOGIN = "instagram_login"         # separate, only when configured + tested
    NONE = "none"


class SyncState(str, Enum):
    NOT_SYNCED = "not_synced"
    SYNC_PENDING = "sync_pending"
    SYNCED = "synced"
    SYNC_FAILED = "sync_failed"


class ImportState(str, Enum):
    STARTED = "started"
    VALIDATING = "validating"
    AWAITING_FILES = "awaiting_files"
    READY_TO_COMMIT = "ready_to_commit"
    COMMITTED = "committed"
    FAILED = "failed"


class ErrorClass(str, Enum):
    """Retry classification for publish attempts."""

    TRANSIENT = "transient"            # network/5xx/confirmed rate limit → backoff
    RATE_LIMIT = "rate_limit"          # honoring provider retry hints
    PAYLOAD = "payload"                # invalid caption/media → permanent
    AUTH = "auth"                      # expired/revoked token/missing scope → pause + reauth
    RESTRICTION = "restriction"        # account/integrity → circuit breaker
    AMBIGUOUS = "ambiguous"            # may have been accepted → UNKNOWN_OUTCOME, reconcile
    UNKNOWN = "unknown"
