"""Local SQLite schema and forward-only migrations.

Migrations are applied idempotently and are never destructive on startup. Adding a
migration means appending to ``MIGRATIONS`` — never editing an applied one, so the D1
schema can mirror versions exactly.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS campaigns (
            campaign_id      TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            campaign_tag     TEXT NOT NULL,
            default_timezone TEXT NOT NULL,
            start_date       TEXT NOT NULL,
            end_date         TEXT NOT NULL,
            schema_version   TEXT NOT NULL DEFAULT '1.7',
            created_at       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS campaign_revisions (
            revision_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id   TEXT NOT NULL REFERENCES campaigns(campaign_id),
            manifest_hash TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            created_by    TEXT NOT NULL DEFAULT 'operator',
            notes         TEXT NOT NULL DEFAULT '',
            UNIQUE(campaign_id, manifest_hash)
        );

        CREATE TABLE IF NOT EXISTS posts (
            post_id              TEXT NOT NULL,
            campaign_id          TEXT NOT NULL REFERENCES campaigns(campaign_id),
            revision_id          INTEGER NOT NULL,
            image_id             INTEGER NOT NULL,
            scheduled_at         TEXT NOT NULL,
            timezone             TEXT NOT NULL,
            platforms            TEXT NOT NULL,
            caption              TEXT NOT NULL DEFAULT '',
            facebook_caption     TEXT NOT NULL DEFAULT '',
            instagram_caption    TEXT NOT NULL DEFAULT '',
            alt_text             TEXT NOT NULL DEFAULT '',
            destination_url      TEXT NOT NULL DEFAULT '',
            grace_minutes        INTEGER,
            campaign_tag         TEXT NOT NULL DEFAULT '',
            ai_disclosure_status TEXT NOT NULL DEFAULT 'not_reviewed',
            enabled              INTEGER NOT NULL DEFAULT 0,
            notes                TEXT NOT NULL DEFAULT '',
            updated_at           TEXT NOT NULL,
            PRIMARY KEY (campaign_id, revision_id, post_id)
        );
        CREATE INDEX IF NOT EXISTS idx_posts_image_id ON posts(image_id);

        CREATE TABLE IF NOT EXISTS media_assets (
            image_id          INTEGER PRIMARY KEY,
            filename          TEXT NOT NULL,
            sha256            TEXT NOT NULL,
            byte_size         INTEGER NOT NULL,
            mime              TEXT NOT NULL DEFAULT 'image/jpeg',
            width             INTEGER NOT NULL DEFAULT 0,
            height            INTEGER NOT NULL DEFAULT 0,
            local_path        TEXT NOT NULL DEFAULT '',
            remote_object_key TEXT NOT NULL DEFAULT '',
            production_state  TEXT NOT NULL DEFAULT 'prompt_ready',
            sync_state        TEXT NOT NULL DEFAULT 'not_synced',
            approved          INTEGER NOT NULL DEFAULT 0,
            zip_part          TEXT NOT NULL DEFAULT '',
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS platform_jobs (
            job_id            INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id       TEXT NOT NULL,
            revision_id       INTEGER NOT NULL,
            post_id           TEXT NOT NULL,
            platform          TEXT NOT NULL,
            target_account_id TEXT NOT NULL DEFAULT '',
            status            TEXT NOT NULL DEFAULT 'DRAFT',
            scheduled_at      TEXT NOT NULL DEFAULT '',
            timezone          TEXT NOT NULL DEFAULT '',
            due_at_utc        TEXT NOT NULL DEFAULT '',
            idempotency_key   TEXT NOT NULL,
            attempt_count     INTEGER NOT NULL DEFAULT 0,
            next_retry_at     TEXT NOT NULL DEFAULT '',
            lease_owner       TEXT NOT NULL DEFAULT '',
            lease_expires_at  TEXT NOT NULL DEFAULT '',
            remote_post_id    TEXT NOT NULL DEFAULT '',
            permalink         TEXT NOT NULL DEFAULT '',
            last_error_class  TEXT NOT NULL DEFAULT 'unknown',
            last_stage        TEXT NOT NULL DEFAULT '',
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            UNIQUE(idempotency_key),
            UNIQUE(campaign_id, revision_id, post_id, platform)
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status_due ON platform_jobs(status, due_at_utc);
        CREATE INDEX IF NOT EXISTS idx_jobs_post ON platform_jobs(post_id);

        CREATE TABLE IF NOT EXISTS publish_attempts (
            attempt_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id           INTEGER NOT NULL REFERENCES platform_jobs(job_id),
            post_id          TEXT NOT NULL,
            platform         TEXT NOT NULL,
            stage            TEXT NOT NULL,
            correlation_id   TEXT NOT NULL,
            attempted_at     TEXT NOT NULL,
            response_summary TEXT NOT NULL DEFAULT '',
            error_class      TEXT NOT NULL DEFAULT 'unknown',
            retry_decision   TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_attempts_job ON publish_attempts(job_id, attempted_at);

        CREATE TABLE IF NOT EXISTS connections (
            connection_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            provider           TEXT NOT NULL UNIQUE,
            auth_flow          TEXT NOT NULL DEFAULT 'none',
            state              TEXT NOT NULL DEFAULT 'not_connected',
            account_id         TEXT NOT NULL DEFAULT '',
            account_name       TEXT NOT NULL DEFAULT '',
            page_id            TEXT NOT NULL DEFAULT '',
            page_name          TEXT NOT NULL DEFAULT '',
            scopes             TEXT NOT NULL DEFAULT '',
            issued_at          TEXT NOT NULL DEFAULT '',
            expires_at         TEXT NOT NULL DEFAULT '',
            last_validated_at  TEXT NOT NULL DEFAULT '',
            activation_state   TEXT NOT NULL DEFAULT 'Not configured',
            key_id             TEXT NOT NULL DEFAULT '',
            updated_at         TEXT NOT NULL
        );

        -- Token ciphertext is isolated from the readable connection metadata.
        CREATE TABLE IF NOT EXISTS connection_tokens (
            connection_id INTEGER PRIMARY KEY REFERENCES connections(connection_id),
            key_id        TEXT NOT NULL,
            nonce         BLOB NOT NULL,
            ciphertext    BLOB NOT NULL,
            created_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS incidents (
            incident_id     TEXT PRIMARY KEY,
            severity        TEXT NOT NULL,
            cause           TEXT NOT NULL,
            platform        TEXT,
            post_id         TEXT NOT NULL DEFAULT '',
            diagnosis       TEXT NOT NULL DEFAULT '',
            remediation     TEXT NOT NULL DEFAULT '',
            retry_eligible  INTEGER NOT NULL DEFAULT 0,
            state           TEXT NOT NULL DEFAULT 'open',
            created_at      TEXT NOT NULL,
            acknowledged_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_incidents_state ON incidents(state, created_at);

        CREATE TABLE IF NOT EXISTS audit_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor    TEXT NOT NULL,
            action   TEXT NOT NULL,
            target   TEXT NOT NULL,
            detail   TEXT NOT NULL DEFAULT '',
            at       TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_events(at);

        CREATE TABLE IF NOT EXISTS import_sessions (
            session_id      TEXT PRIMARY KEY,
            state           TEXT NOT NULL,
            plan_hash       TEXT NOT NULL DEFAULT '',
            manifest_json   TEXT NOT NULL DEFAULT '',
            verified_hashes TEXT NOT NULL DEFAULT '{}',
            archive_ranges  TEXT NOT NULL DEFAULT '[]',
            checkpoint      TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notification_health (
            channel        TEXT PRIMARY KEY,
            configured     INTEGER NOT NULL DEFAULT 0,
            last_test_at   TEXT NOT NULL DEFAULT '',
            last_test_ok   INTEGER NOT NULL DEFAULT 0,
            last_digest_at TEXT NOT NULL DEFAULT '',
            detail         TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS backup_runs (
            backup_id        TEXT PRIMARY KEY,
            path             TEXT NOT NULL,
            created_at       TEXT NOT NULL,
            byte_size        INTEGER NOT NULL DEFAULT 0,
            includes_secrets INTEGER NOT NULL DEFAULT 0,
            verified         INTEGER NOT NULL DEFAULT 0,
            restore_drill_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS oauth_states (
            state        TEXT PRIMARY KEY,
            provider     TEXT NOT NULL,
            code_verifier TEXT NOT NULL DEFAULT '',
            created_at   TEXT NOT NULL,
            expires_at   TEXT NOT NULL
        );
        """,
    ),
    (
        2,
        """
        -- Instagram publishes persist their media-container id across scheduler ticks.
        ALTER TABLE platform_jobs ADD COLUMN container_id TEXT NOT NULL DEFAULT '';

        -- Runtime flags: global/per-platform pause and other durable operator switches.
        CREATE TABLE IF NOT EXISTS runtime_flags (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        """,
    ),
]

SCHEMA_VERSION = max(version for version, _ in MIGRATIONS)


def current_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT)")
    row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    return int(row["v"]) if row and row["v"] is not None else 0


def migrate(conn: sqlite3.Connection) -> int:
    """Apply all pending migrations. Safe to call on every startup."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT)")
    applied = current_version(conn)
    for version, sql in MIGRATIONS:
        if version <= applied:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, datetime.utcnow().isoformat(timespec="seconds") + "Z"),
        )
    return SCHEMA_VERSION
