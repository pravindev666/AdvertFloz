"""Repository over local SQLite.

Semantics deliberately mirror the D1 remote schema so the same domain rules apply in
both planes (PRD §6). Claims and state transitions run inside IMMEDIATE transactions.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ....domain.enums import (
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
from ....domain.models import (
    AuditEvent,
    BackupRun,
    Campaign,
    CampaignRevision,
    Connection,
    ImportSession,
    Incident,
    MediaAsset,
    NotificationHealth,
    PlatformJob,
    Post,
    PublishAttempt,
)
from .connection import connect, transaction
from .migrations import migrate


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


class Repository:
    """All durable state access for local mode.

    Connections are thread-local: Streamlit runs each script run on its own thread, and a SQLite
    connection must not be shared across threads. Each thread lazily gets its own connection with
    migrations already applied.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._local = threading.local()
        self._ensure_conn()

    def _ensure_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = connect(self.db_path)
            migrate(conn)
            self._local.conn = conn
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._ensure_conn()

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ------------------------------------------------------------- campaigns
    def upsert_campaign(self, campaign: Campaign) -> None:
        self.conn.execute(
            """
            INSERT INTO campaigns(campaign_id, name, campaign_tag, default_timezone, start_date, end_date, schema_version, created_at)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(campaign_id) DO UPDATE SET
                name=excluded.name, campaign_tag=excluded.campaign_tag,
                default_timezone=excluded.default_timezone, start_date=excluded.start_date,
                end_date=excluded.end_date, schema_version=excluded.schema_version
            """,
            (
                campaign.campaign_id, campaign.name, campaign.campaign_tag, campaign.default_timezone,
                campaign.start_date, campaign.end_date, campaign.schema_version, campaign.created_at,
            ),
        )

    def get_campaign(self, campaign_id: str) -> Campaign | None:
        row = self.conn.execute("SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
        if not row:
            return None
        return Campaign(
            campaign_id=row["campaign_id"], name=row["name"], campaign_tag=row["campaign_tag"],
            default_timezone=row["default_timezone"], start_date=row["start_date"],
            end_date=row["end_date"], schema_version=row["schema_version"], created_at=row["created_at"],
        )

    def list_campaigns(self) -> list[Campaign]:
        rows = self.conn.execute("SELECT campaign_id FROM campaigns ORDER BY created_at").fetchall()
        return [c for c in (self.get_campaign(r["campaign_id"]) for r in rows) if c]

    def delete_campaign(self, campaign_id: str) -> None:
        with transaction(self.conn):
            self.conn.execute("DELETE FROM platform_jobs WHERE campaign_id=?", (campaign_id,))
            self.conn.execute("DELETE FROM posts WHERE campaign_id=?", (campaign_id,))
            self.conn.execute("DELETE FROM campaign_revisions WHERE campaign_id=?", (campaign_id,))
            self.conn.execute("DELETE FROM campaigns WHERE campaign_id=?", (campaign_id,))

    # ------------------------------------------------------------- revisions
    def create_revision(self, campaign_id: str, manifest_hash: str, created_by: str = "operator", notes: str = "") -> int:
        with transaction(self.conn):
            existing = self.conn.execute(
                "SELECT revision_id FROM campaign_revisions WHERE campaign_id=? AND manifest_hash=?",
                (campaign_id, manifest_hash),
            ).fetchone()
            if existing:
                return int(existing["revision_id"])
            cur = self.conn.execute(
                "INSERT INTO campaign_revisions(campaign_id, manifest_hash, created_at, created_by, notes) VALUES (?,?,?,?,?)",
                (campaign_id, manifest_hash, _now(), created_by, notes),
            )
            return int(cur.lastrowid)

    def get_revision(self, revision_id: int) -> CampaignRevision | None:
        row = self.conn.execute("SELECT * FROM campaign_revisions WHERE revision_id=?", (revision_id,)).fetchone()
        if not row:
            return None
        return CampaignRevision(
            revision_id=row["revision_id"], campaign_id=row["campaign_id"], manifest_hash=row["manifest_hash"],
            created_at=row["created_at"], created_by=row["created_by"], notes=row["notes"],
        )

    def latest_revision(self, campaign_id: str) -> CampaignRevision | None:
        row = self.conn.execute(
            "SELECT * FROM campaign_revisions WHERE campaign_id=? ORDER BY revision_id DESC LIMIT 1", (campaign_id,)
        ).fetchone()
        return self.get_revision(int(row["revision_id"])) if row else None

    # ------------------------------------------------------------- posts
    def upsert_post(self, post: Post) -> None:
        self.conn.execute(
            """
            INSERT INTO posts(post_id, campaign_id, revision_id, image_id, scheduled_at, timezone, platforms,
                              caption, facebook_caption, instagram_caption, alt_text, destination_url, grace_minutes,
                              campaign_tag, ai_disclosure_status, enabled, notes, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(campaign_id, revision_id, post_id) DO UPDATE SET
                image_id=excluded.image_id, scheduled_at=excluded.scheduled_at, timezone=excluded.timezone,
                platforms=excluded.platforms, caption=excluded.caption, facebook_caption=excluded.facebook_caption,
                instagram_caption=excluded.instagram_caption, alt_text=excluded.alt_text,
                destination_url=excluded.destination_url, grace_minutes=excluded.grace_minutes,
                campaign_tag=excluded.campaign_tag, ai_disclosure_status=excluded.ai_disclosure_status,
                enabled=excluded.enabled, notes=excluded.notes, updated_at=excluded.updated_at
            """,
            (
                post.post_id, post.campaign_id, post.revision_id, post.image_id, post.scheduled_at, post.timezone,
                ";".join(p.value for p in post.platforms), post.caption, post.facebook_caption,
                post.instagram_caption, post.alt_text, post.destination_url, post.grace_minutes, post.campaign_tag,
                post.ai_disclosure_status.value, 1 if post.enabled else 0, post.notes, _now(),
            ),
        )

    def _row_to_post(self, row: sqlite3.Row) -> Post:
        platforms = tuple(Platform(p) for p in row["platforms"].split(";") if p)
        return Post(
            post_id=row["post_id"], campaign_id=row["campaign_id"], revision_id=row["revision_id"],
            image_id=row["image_id"], scheduled_at=row["scheduled_at"], timezone=row["timezone"],
            platforms=platforms, caption=row["caption"], facebook_caption=row["facebook_caption"],
            instagram_caption=row["instagram_caption"], alt_text=row["alt_text"],
            destination_url=row["destination_url"], grace_minutes=row["grace_minutes"],
            campaign_tag=row["campaign_tag"], ai_disclosure_status=DisclosureStatus(row["ai_disclosure_status"]),
            enabled=bool(row["enabled"]), notes=row["notes"],
        )

    def get_post(self, campaign_id: str, revision_id: int, post_id: str) -> Post | None:
        row = self.conn.execute(
            "SELECT * FROM posts WHERE campaign_id=? AND revision_id=? AND post_id=?",
            (campaign_id, revision_id, post_id),
        ).fetchone()
        return self._row_to_post(row) if row else None

    def list_posts(self, campaign_id: str, revision_id: int) -> list[Post]:
        rows = self.conn.execute(
            "SELECT * FROM posts WHERE campaign_id=? AND revision_id=? ORDER BY post_id", (campaign_id, revision_id)
        ).fetchall()
        return [self._row_to_post(r) for r in rows]

    def set_post_enabled(self, campaign_id: str, revision_id: int, post_id: str, enabled: bool) -> None:
        self.conn.execute(
            "UPDATE posts SET enabled=?, updated_at=? WHERE campaign_id=? AND revision_id=? AND post_id=?",
            (1 if enabled else 0, _now(), campaign_id, revision_id, post_id),
        )

    def update_post_schedule(self, campaign_id: str, revision_id: int, post_id: str, scheduled_at: str, timezone_name: str) -> None:
        self.conn.execute(
            "UPDATE posts SET scheduled_at=?, timezone=?, updated_at=? WHERE campaign_id=? AND revision_id=? AND post_id=?",
            (scheduled_at, timezone_name, _now(), campaign_id, revision_id, post_id),
        )

    # ------------------------------------------------------------- media assets
    def upsert_asset(self, asset: MediaAsset) -> None:
        self.conn.execute(
            """
            INSERT INTO media_assets(image_id, filename, sha256, byte_size, mime, width, height, local_path,
                                     remote_object_key, production_state, sync_state, approved, zip_part, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(image_id) DO UPDATE SET
                filename=excluded.filename, sha256=excluded.sha256, byte_size=excluded.byte_size, mime=excluded.mime,
                width=excluded.width, height=excluded.height, local_path=excluded.local_path,
                remote_object_key=excluded.remote_object_key, production_state=excluded.production_state,
                sync_state=excluded.sync_state, approved=excluded.approved, zip_part=excluded.zip_part,
                updated_at=excluded.updated_at
            """,
            (
                asset.image_id, asset.filename, asset.sha256, asset.byte_size, asset.mime, asset.width,
                asset.height, asset.local_path, asset.remote_object_key, asset.production_state.value,
                asset.sync_state.value, 1 if asset.approved else 0, asset.zip_part, asset.created_at, _now(),
            ),
        )

    def _row_to_asset(self, row: sqlite3.Row) -> MediaAsset:
        return MediaAsset(
            image_id=row["image_id"], filename=row["filename"], sha256=row["sha256"], byte_size=row["byte_size"],
            mime=row["mime"], width=row["width"], height=row["height"], local_path=row["local_path"],
            remote_object_key=row["remote_object_key"], production_state=ProductionState(row["production_state"]),
            sync_state=SyncState(row["sync_state"]), approved=bool(row["approved"]), zip_part=row["zip_part"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def get_asset(self, image_id: int) -> MediaAsset | None:
        row = self.conn.execute("SELECT * FROM media_assets WHERE image_id=?", (image_id,)).fetchone()
        return self._row_to_asset(row) if row else None

    def list_assets(self) -> list[MediaAsset]:
        rows = self.conn.execute("SELECT * FROM media_assets ORDER BY image_id").fetchall()
        return [self._row_to_asset(r) for r in rows]

    def update_production_state(self, image_id: int, state: ProductionState, approved: bool | None = None) -> None:
        if approved is None:
            self.conn.execute(
                "UPDATE media_assets SET production_state=?, updated_at=? WHERE image_id=?",
                (state.value, _now(), image_id),
            )
        else:
            self.conn.execute(
                "UPDATE media_assets SET production_state=?, approved=?, updated_at=? WHERE image_id=?",
                (state.value, 1 if approved else 0, _now(), image_id),
            )

    def update_sync_state(self, image_id: int, sync_state: SyncState, remote_object_key: str = "") -> None:
        if remote_object_key:
            self.conn.execute(
                "UPDATE media_assets SET sync_state=?, remote_object_key=?, updated_at=? WHERE image_id=?",
                (sync_state.value, remote_object_key, _now(), image_id),
            )
        else:
            self.conn.execute(
                "UPDATE media_assets SET sync_state=?, updated_at=? WHERE image_id=?",
                (sync_state.value, _now(), image_id),
            )

    def ready_synced_image_ids(self) -> set[int]:
        rows = self.conn.execute(
            "SELECT image_id FROM media_assets WHERE approved=1 AND sync_state='synced'"
        ).fetchall()
        return {int(r["image_id"]) for r in rows}

    # ------------------------------------------------------------- jobs
    def ensure_job(self, job: PlatformJob) -> int:
        row = self.conn.execute(
            "SELECT job_id FROM platform_jobs WHERE idempotency_key=?", (job.idempotency_key,)
        ).fetchone()
        if row:
            return int(row["job_id"])
        cur = self.conn.execute(
            """
            INSERT INTO platform_jobs(campaign_id, revision_id, post_id, platform, target_account_id, status,
                                      scheduled_at, timezone, due_at_utc, idempotency_key, attempt_count, next_retry_at,
                                      lease_owner, lease_expires_at, remote_post_id, permalink, last_error_class,
                                      last_stage, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                job.campaign_id, job.revision_id, job.post_id, job.platform.value, job.target_account_id,
                job.status.value, job.scheduled_at, job.timezone, job.due_at_utc, job.idempotency_key,
                job.attempt_count, job.next_retry_at, job.lease_owner, job.lease_expires_at, job.remote_post_id,
                job.permalink, job.last_error_class.value, job.last_stage, job.created_at, _now(),
            ),
        )
        return int(cur.lastrowid)

    def _row_to_job(self, row: sqlite3.Row) -> PlatformJob:
        job = PlatformJob(
            post_id=row["post_id"], platform=Platform(row["platform"]), campaign_id=row["campaign_id"],
            revision_id=row["revision_id"], target_account_id=row["target_account_id"],
            status=JobStatus(row["status"]), scheduled_at=row["scheduled_at"], timezone=row["timezone"],
            idempotency_key=row["idempotency_key"], attempt_count=row["attempt_count"],
            next_retry_at=row["next_retry_at"], lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"], remote_post_id=row["remote_post_id"],
            permalink=row["permalink"], last_error_class=ErrorClass(row["last_error_class"]),
            last_stage=row["last_stage"], container_id=row["container_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
        job.job_id = int(row["job_id"])          # type: ignore[attr-defined]
        job.due_at_utc = row["due_at_utc"]       # type: ignore[attr-defined]
        return job

    def get_job(self, job_id: int) -> PlatformJob | None:
        row = self.conn.execute("SELECT * FROM platform_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(
        self,
        *,
        campaign_id: str | None = None,
        revision_id: int | None = None,
        post_id: str | None = None,
        platform: Platform | None = None,
        statuses: Iterable[JobStatus] | None = None,
    ) -> list[PlatformJob]:
        clauses, params = [], []
        if campaign_id:
            clauses.append("campaign_id=?")
            params.append(campaign_id)
        if revision_id is not None:
            clauses.append("revision_id=?")
            params.append(revision_id)
        if post_id:
            clauses.append("post_id=?")
            params.append(post_id)
        if platform:
            clauses.append("platform=?")
            params.append(platform.value)
        if statuses:
            values = [s.value for s in statuses]
            clauses.append(f"status IN ({','.join('?' * len(values))})")
            params.extend(values)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM platform_jobs {where} ORDER BY due_at_utc, post_id", params
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def count_jobs_by_status(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT status, COUNT(*) AS n FROM platform_jobs GROUP BY status").fetchall()
        return {r["status"]: int(r["n"]) for r in rows}

    def claim_due_jobs(
        self, claimable: Iterable[JobStatus], now: datetime, limit: int, owner: str, lease_seconds: int
    ) -> list[PlatformJob]:
        """Atomically claim up to ``limit`` due jobs, including stale leases."""
        now_iso = _iso(now)
        lease_until = _iso(now + timedelta(seconds=lease_seconds))
        statuses = [s.value for s in claimable]
        placeholders = ",".join("?" * len(statuses))
        claimed: list[int] = []
        with transaction(self.conn):
            rows = self.conn.execute(
                f"""
                SELECT job_id FROM platform_jobs
                WHERE status IN ({placeholders})
                  AND due_at_utc != '' AND due_at_utc <= ?
                  AND (next_retry_at = '' OR next_retry_at <= ?)
                  AND (lease_expires_at = '' OR lease_expires_at <= ?)
                ORDER BY due_at_utc
                LIMIT ?
                """,
                (*statuses, now_iso, now_iso, now_iso, limit),
            ).fetchall()
            for row in rows:
                cur = self.conn.execute(
                    """
                    UPDATE platform_jobs
                    SET status=?, lease_owner=?, lease_expires_at=?, updated_at=?
                    WHERE job_id=? AND (lease_expires_at='' OR lease_expires_at<=?)
                    """,
                    (JobStatus.CLAIMED.value, owner, lease_until, now_iso, row["job_id"], now_iso),
                )
                if cur.rowcount == 1:
                    claimed.append(int(row["job_id"]))
        return [j for j in (self.get_job(i) for i in claimed) if j]

    def release_expired_leases(self, now: datetime) -> int:
        cur = self.conn.execute(
            """
            UPDATE platform_jobs SET status=?, lease_owner='', lease_expires_at='', updated_at=?
            WHERE status=? AND lease_expires_at != '' AND lease_expires_at <= ?
            """,
            (JobStatus.QUEUED.value, _iso(now), JobStatus.CLAIMED.value, _iso(now)),
        )
        return cur.rowcount

    def transition_job(
        self,
        job_id: int,
        status: JobStatus,
        *,
        lease_owner: str | None = None,
        clear_lease: bool = False,
        last_stage: str | None = None,
        last_error_class: ErrorClass | None = None,
        next_retry_at: str | None = None,
        increment_attempt: bool = False,
        remote_post_id: str | None = None,
        permalink: str | None = None,
    ) -> None:
        sets = ["status=?", "updated_at=?"]
        params: list = [status.value, _now()]
        if clear_lease:
            sets += ["lease_owner=''", "lease_expires_at=''"]
        elif lease_owner is not None:
            sets.append("lease_owner=?")
            params.append(lease_owner)
        if last_stage is not None:
            sets.append("last_stage=?")
            params.append(last_stage)
        if last_error_class is not None:
            sets.append("last_error_class=?")
            params.append(last_error_class.value)
        if next_retry_at is not None:
            sets.append("next_retry_at=?")
            params.append(next_retry_at)
        if increment_attempt:
            sets.append("attempt_count=attempt_count+1")
        if remote_post_id is not None:
            sets.append("remote_post_id=?")
            params.append(remote_post_id)
        if permalink is not None:
            sets.append("permalink=?")
            params.append(permalink)
        params.append(job_id)
        self.conn.execute(f"UPDATE platform_jobs SET {', '.join(sets)} WHERE job_id=?", params)

    # ------------------------------------------------------------- attempts
    def record_attempt(self, attempt: PublishAttempt, job_id: int | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO publish_attempts(job_id, post_id, platform, stage, correlation_id, attempted_at,
                                         response_summary, error_class, retry_decision)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                job_id or 0, attempt.post_id, attempt.platform.value, attempt.stage, attempt.correlation_id,
                attempt.attempted_at, attempt.response_summary, attempt.error_class.value, attempt.retry_decision,
            ),
        )

    def list_attempts(self, job_id: int) -> list[PublishAttempt]:
        rows = self.conn.execute(
            "SELECT * FROM publish_attempts WHERE job_id=? ORDER BY attempted_at", (job_id,)
        ).fetchall()
        return [
            PublishAttempt(
                post_id=r["post_id"], platform=Platform(r["platform"]), stage=r["stage"],
                correlation_id=r["correlation_id"], attempted_at=r["attempted_at"],
                response_summary=r["response_summary"], error_class=ErrorClass(r["error_class"]),
                retry_decision=r["retry_decision"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------- connections
    def upsert_connection(self, conn: Connection) -> int:
        self.conn.execute(
            """
            INSERT INTO connections(provider, auth_flow, state, account_id, account_name, page_id, page_name,
                                    scopes, issued_at, expires_at, last_validated_at, activation_state, key_id, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(provider) DO UPDATE SET
                auth_flow=excluded.auth_flow, state=excluded.state, account_id=excluded.account_id,
                account_name=excluded.account_name, page_id=excluded.page_id, page_name=excluded.page_name,
                scopes=excluded.scopes, issued_at=excluded.issued_at, expires_at=excluded.expires_at,
                last_validated_at=excluded.last_validated_at, activation_state=excluded.activation_state,
                key_id=excluded.key_id, updated_at=excluded.updated_at
            """,
            (
                conn.provider.value, conn.auth_flow.value, conn.state.value, conn.account_id, conn.account_name,
                conn.page_id, conn.page_name, " ".join(conn.scopes), conn.issued_at, conn.expires_at,
                conn.last_validated_at, conn.activation_state.value, conn.key_id, _now(),
            ),
        )
        row = self.conn.execute("SELECT connection_id FROM connections WHERE provider=?", (conn.provider.value,)).fetchone()
        return int(row["connection_id"])

    def get_connection(self, provider: Platform) -> Connection | None:
        row = self.conn.execute("SELECT * FROM connections WHERE provider=?", (provider.value,)).fetchone()
        if not row:
            return None
        return Connection(
            provider=Platform(row["provider"]), auth_flow=AuthFlow(row["auth_flow"]),
            state=ConnectionState(row["state"]), account_id=row["account_id"], account_name=row["account_name"],
            page_id=row["page_id"], page_name=row["page_name"],
            scopes=tuple(s for s in row["scopes"].split(" ") if s), issued_at=row["issued_at"],
            expires_at=row["expires_at"], last_validated_at=row["last_validated_at"],
            activation_state=ActivationState(row["activation_state"]), key_id=row["key_id"],
            updated_at=row["updated_at"],
        )

    def connection_id(self, provider: Platform) -> int | None:
        row = self.conn.execute("SELECT connection_id FROM connections WHERE provider=?", (provider.value,)).fetchone()
        return int(row["connection_id"]) if row else None

    def store_token(self, provider: Platform, key_id: str, nonce: bytes, ciphertext: bytes) -> None:
        cid = self.connection_id(provider)
        if cid is None:
            raise ValueError(f"no connection row for {provider.value}")
        self.conn.execute(
            """
            INSERT INTO connection_tokens(connection_id, key_id, nonce, ciphertext, created_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(connection_id) DO UPDATE SET
                key_id=excluded.key_id, nonce=excluded.nonce, ciphertext=excluded.ciphertext, created_at=excluded.created_at
            """,
            (cid, key_id, nonce, ciphertext, _now()),
        )

    def get_token_blob(self, provider: Platform) -> tuple[str, bytes, bytes] | None:
        row = self.conn.execute(
            "SELECT t.key_id AS key_id, t.nonce AS nonce, t.ciphertext AS ciphertext "
            "FROM connection_tokens t JOIN connections c ON c.connection_id=t.connection_id WHERE c.provider=?",
            (provider.value,),
        ).fetchone()
        if not row:
            return None
        return row["key_id"], bytes(row["nonce"]), bytes(row["ciphertext"])

    def delete_token(self, provider: Platform) -> None:
        cid = self.connection_id(provider)
        if cid is not None:
            self.conn.execute("DELETE FROM connection_tokens WHERE connection_id=?", (cid,))

    # ------------------------------------------------------------- incidents
    def add_incident(self, incident: Incident) -> None:
        self.conn.execute(
            """
            INSERT INTO incidents(incident_id, severity, cause, platform, post_id, diagnosis, remediation,
                                  retry_eligible, state, created_at, acknowledged_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(incident_id) DO UPDATE SET
                severity=excluded.severity, diagnosis=excluded.diagnosis, remediation=excluded.remediation,
                retry_eligible=excluded.retry_eligible, state=excluded.state
            """,
            (
                incident.incident_id, incident.severity.value, incident.cause,
                incident.platform.value if incident.platform else None, incident.post_id, incident.diagnosis,
                incident.remediation, 1 if incident.retry_eligible else 0, incident.state.value,
                incident.created_at, incident.acknowledged_at,
            ),
        )

    def _row_to_incident(self, row: sqlite3.Row) -> Incident:
        return Incident(
            incident_id=row["incident_id"], severity=Severity(row["severity"]), cause=row["cause"],
            platform=Platform(row["platform"]) if row["platform"] else None, post_id=row["post_id"],
            diagnosis=row["diagnosis"], remediation=row["remediation"], retry_eligible=bool(row["retry_eligible"]),
            state=IncidentState(row["state"]), created_at=row["created_at"], acknowledged_at=row["acknowledged_at"],
        )

    def list_incidents(self, state: IncidentState | None = None) -> list[Incident]:
        if state is None:
            rows = self.conn.execute("SELECT * FROM incidents ORDER BY created_at DESC").fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM incidents WHERE state=? ORDER BY created_at DESC", (state.value,)).fetchall()
        return [self._row_to_incident(r) for r in rows]

    def acknowledge_incident(self, incident_id: str) -> None:
        self.conn.execute(
            "UPDATE incidents SET state=?, acknowledged_at=? WHERE incident_id=?",
            (IncidentState.ACKNOWLEDGED.value, _now(), incident_id),
        )

    # ------------------------------------------------------------- audit
    def audit(self, actor: str, action: str, target: str, detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO audit_events(actor, action, target, detail, at) VALUES (?,?,?,?,?)",
            (actor, action, target, detail, _now()),
        )

    def list_audit(self, limit: int = 500) -> list[AuditEvent]:
        rows = self.conn.execute("SELECT * FROM audit_events ORDER BY at DESC LIMIT ?", (limit,)).fetchall()
        return [
            AuditEvent(actor=r["actor"], action=r["action"], target=r["target"], detail=r["detail"], at=r["at"])
            for r in rows
        ]

    # ------------------------------------------------------------- import sessions
    def upsert_import_session(self, session: ImportSession) -> None:
        self.conn.execute(
            """
            INSERT INTO import_sessions(session_id, state, plan_hash, manifest_json, verified_hashes, archive_ranges,
                                        checkpoint, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(session_id) DO UPDATE SET
                state=excluded.state, plan_hash=excluded.plan_hash, manifest_json=excluded.manifest_json,
                verified_hashes=excluded.verified_hashes, archive_ranges=excluded.archive_ranges,
                checkpoint=excluded.checkpoint, updated_at=excluded.updated_at
            """,
            (
                session.session_id, session.state, session.plan_hash, session.manifest_json,
                session.verified_hashes, session.archive_ranges, session.checkpoint, session.created_at, _now(),
            ),
        )

    def get_import_session(self, session_id: str) -> ImportSession | None:
        row = self.conn.execute("SELECT * FROM import_sessions WHERE session_id=?", (session_id,)).fetchone()
        if not row:
            return None
        return ImportSession(
            session_id=row["session_id"], state=row["state"], plan_hash=row["plan_hash"],
            manifest_json=row["manifest_json"], verified_hashes=row["verified_hashes"],
            archive_ranges=row["archive_ranges"], checkpoint=row["checkpoint"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    # ------------------------------------------------------------- notification health
    def upsert_notification_health(self, health: NotificationHealth) -> None:
        self.conn.execute(
            """
            INSERT INTO notification_health(channel, configured, last_test_at, last_test_ok, last_digest_at, detail)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(channel) DO UPDATE SET
                configured=excluded.configured, last_test_at=excluded.last_test_at, last_test_ok=excluded.last_test_ok,
                last_digest_at=excluded.last_digest_at, detail=excluded.detail
            """,
            (
                health.channel, 1 if health.configured else 0, health.last_test_at, 1 if health.last_test_ok else 0,
                health.last_digest_at, health.detail,
            ),
        )

    def get_notification_health(self, channel: str = "telegram") -> NotificationHealth:
        row = self.conn.execute("SELECT * FROM notification_health WHERE channel=?", (channel,)).fetchone()
        if not row:
            return NotificationHealth(channel=channel)
        return NotificationHealth(
            channel=row["channel"], configured=bool(row["configured"]), last_test_at=row["last_test_at"],
            last_test_ok=bool(row["last_test_ok"]), last_digest_at=row["last_digest_at"], detail=row["detail"],
        )

    # ------------------------------------------------------------- backups
    def add_backup_run(self, run: BackupRun) -> None:
        self.conn.execute(
            """
            INSERT INTO backup_runs(backup_id, path, created_at, byte_size, includes_secrets, verified, restore_drill_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(backup_id) DO UPDATE SET
                path=excluded.path, byte_size=excluded.byte_size, includes_secrets=excluded.includes_secrets,
                verified=excluded.verified, restore_drill_at=excluded.restore_drill_at
            """,
            (
                run.backup_id, run.path, run.created_at, run.byte_size, 1 if run.includes_secrets else 0,
                1 if run.verified else 0, run.restore_drill_at,
            ),
        )

    def list_backup_runs(self) -> list[BackupRun]:
        rows = self.conn.execute("SELECT * FROM backup_runs ORDER BY created_at DESC").fetchall()
        return [
            BackupRun(
                backup_id=r["backup_id"], path=r["path"], created_at=r["created_at"], byte_size=r["byte_size"],
                includes_secrets=bool(r["includes_secrets"]), verified=bool(r["verified"]),
                restore_drill_at=r["restore_drill_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------- oauth states
    def save_oauth_state(self, state: str, provider: Platform, code_verifier: str, ttl_seconds: int = 600) -> None:
        now = datetime.now(UTC)
        self.conn.execute(
            "INSERT OR REPLACE INTO oauth_states(state, provider, code_verifier, created_at, expires_at) VALUES (?,?,?,?,?)",
            (state, provider.value, code_verifier, _iso(now), _iso(now + timedelta(seconds=ttl_seconds))),
        )

    def consume_oauth_state(self, state: str, provider: Platform) -> str | None:
        """Single-use: returns the code_verifier and deletes the row, or None if invalid/expired."""
        with transaction(self.conn):
            row = self.conn.execute(
                "SELECT * FROM oauth_states WHERE state=? AND provider=?", (state, provider.value)
            ).fetchone()
            self.conn.execute("DELETE FROM oauth_states WHERE state=?", (state,))
        if not row:
            return None
        if row["expires_at"] <= _iso(datetime.now(UTC)):
            return None
        return row["code_verifier"]

    def purge_expired_oauth_states(self) -> int:
        cur = self.conn.execute("DELETE FROM oauth_states WHERE expires_at <= ?", (_iso(datetime.now(UTC)),))
        return cur.rowcount

    def consume_oauth_state_any(self, state: str) -> tuple[Platform, str] | None:
        """Single-use state consumption that infers the provider. Returns (provider, verifier)."""
        with transaction(self.conn):
            row = self.conn.execute("SELECT * FROM oauth_states WHERE state=?", (state,)).fetchone()
            self.conn.execute("DELETE FROM oauth_states WHERE state=?", (state,))
        if not row:
            return None
        if row["expires_at"] <= _iso(datetime.now(UTC)):
            return None
        return Platform(row["provider"]), row["code_verifier"]

    # ------------------------------------------------------------- runtime flags
    def set_flag(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO runtime_flags(key, value, updated_at) VALUES (?,?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, value, _now()),
        )

    def get_flag(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM runtime_flags WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def pause(self, target: str, actor: str = "operator") -> None:
        """target: 'all' | 'facebook' | 'instagram'."""
        key = "pause_all" if target == "all" else f"pause_{target}"
        self.set_flag(key, "1")
        self.audit(actor, "pause", target, "dispatch paused durably")

    def resume(self, target: str, actor: str = "operator") -> None:
        key = "pause_all" if target == "all" else f"pause_{target}"
        self.set_flag(key, "0")
        self.audit(actor, "resume", target, "dispatch resumed")

    def is_paused(self, platform: Platform) -> bool:
        if self.get_flag("pause_all") == "1":
            return True
        return self.get_flag(f"pause_{platform.value}") == "1"

    def set_container_id(self, job_id: int, container_id: str) -> None:
        self.conn.execute(
            "UPDATE platform_jobs SET container_id=?, updated_at=? WHERE job_id=?",
            (container_id, _now(), job_id),
        )

    # ------------------------------------------------------------- helpers
    def unknown_outcome_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM platform_jobs WHERE status=?", (JobStatus.UNKNOWN_OUTCOME.value,)
        ).fetchone()
        return int(row["n"])

    def oldest_pending_job(self) -> PlatformJob | None:
        row = self.conn.execute(
            "SELECT * FROM platform_jobs WHERE status IN (?,?) ORDER BY due_at_utc LIMIT 1",
            (JobStatus.QUEUED.value, JobStatus.SYNCED.value),
        ).fetchone()
        return self._row_to_job(row) if row else None

    def next_due_job(self, now: datetime) -> PlatformJob | None:
        row = self.conn.execute(
            "SELECT * FROM platform_jobs WHERE due_at_utc >= ? AND status IN (?,?) ORDER BY due_at_utc LIMIT 1",
            (_iso(now), JobStatus.QUEUED.value, JobStatus.SYNCED.value),
        ).fetchone()
        return self._row_to_job(row) if row else None

    def last_published_job(self, platform: Platform) -> PlatformJob | None:
        row = self.conn.execute(
            "SELECT * FROM platform_jobs WHERE platform=? AND status=? ORDER BY updated_at DESC LIMIT 1",
            (platform.value, JobStatus.PUBLISHED.value),
        ).fetchone()
        return self._row_to_job(row) if row else None

    def jobs_due_between(self, now: datetime, until: datetime) -> list[PlatformJob]:
        rows = self.conn.execute(
            "SELECT * FROM platform_jobs WHERE due_at_utc BETWEEN ? AND ? ORDER BY due_at_utc",
            (_iso(now), _iso(until)),
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def export_rows(self, statuses: Iterable[JobStatus] | None = None) -> list[dict]:
        jobs = self.list_jobs(statuses=statuses)
        out = []
        for job in jobs:
            post = self.get_post(job.campaign_id, job.revision_id, job.post_id)
            out.append(
                {
                    "post_id": job.post_id,
                    "platform": job.platform.value,
                    "scheduled_at": job.scheduled_at,
                    "timezone": job.timezone,
                    "status": job.status.value,
                    "remote_post_id": job.remote_post_id,
                    "permalink": job.permalink,
                    "campaign_tag": post.campaign_tag if post else "",
                    "destination_url": post.destination_url if post else "",
                    "error_class": job.last_error_class.value,
                    "attempt_count": job.attempt_count,
                    "updated_at": job.updated_at,
                }
            )
        return out

    def verified_hashes_map(self) -> dict[int, str]:
        return {a.image_id: a.sha256 for a in self.list_assets()}

    def store_verified_hashes(self, session_id: str, hashes: dict[int, str]) -> None:
        session = self.get_import_session(session_id)
        if session is None:
            return
        session.verified_hashes = json.dumps({str(k): v for k, v in hashes.items()})
        self.upsert_import_session(session)
