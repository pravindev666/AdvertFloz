-- AdvertFloz remote plane schema (Cloudflare D1).
-- Semantics mirror the local SQLite schema so the same domain rules apply in both planes.

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
    campaign_id   TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    created_by    TEXT NOT NULL DEFAULT 'operator',
    notes         TEXT NOT NULL DEFAULT '',
    UNIQUE (campaign_id, manifest_hash)
);

CREATE TABLE IF NOT EXISTS posts (
    post_id              TEXT NOT NULL,
    campaign_id          TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS media_assets (
    image_id          INTEGER PRIMARY KEY,
    filename          TEXT NOT NULL,
    sha256            TEXT NOT NULL,
    byte_size         INTEGER NOT NULL,
    mime              TEXT NOT NULL DEFAULT 'image/jpeg',
    width             INTEGER NOT NULL DEFAULT 0,
    height            INTEGER NOT NULL DEFAULT 0,
    remote_object_key TEXT NOT NULL DEFAULT '',
    production_state  TEXT NOT NULL DEFAULT 'prompt_ready',
    sync_state        TEXT NOT NULL DEFAULT 'not_synced',
    approved          INTEGER NOT NULL DEFAULT 0,
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
    idempotency_key   TEXT NOT NULL UNIQUE,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    next_retry_at     TEXT NOT NULL DEFAULT '',
    lease_owner       TEXT NOT NULL DEFAULT '',
    lease_expires_at  TEXT NOT NULL DEFAULT '',
    remote_post_id    TEXT NOT NULL DEFAULT '',
    permalink         TEXT NOT NULL DEFAULT '',
    last_error_class  TEXT NOT NULL DEFAULT 'unknown',
    last_stage        TEXT NOT NULL DEFAULT '',
    container_id      TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE (campaign_id, revision_id, post_id, platform)
);
CREATE INDEX IF NOT EXISTS idx_jobs_status_due ON platform_jobs (status, due_at_utc);

CREATE TABLE IF NOT EXISTS publish_attempts (
    attempt_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id           INTEGER NOT NULL,
    post_id          TEXT NOT NULL,
    platform         TEXT NOT NULL,
    stage            TEXT NOT NULL,
    correlation_id   TEXT NOT NULL,
    attempted_at     TEXT NOT NULL,
    response_summary TEXT NOT NULL DEFAULT '',
    error_class      TEXT NOT NULL DEFAULT 'unknown',
    retry_decision   TEXT NOT NULL DEFAULT ''
);

-- Connection metadata is readable; token ciphertext is isolated and never leaves the Worker.
CREATE TABLE IF NOT EXISTS connections (
    connection_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    provider         TEXT NOT NULL UNIQUE,
    auth_flow        TEXT NOT NULL DEFAULT 'none',
    state            TEXT NOT NULL DEFAULT 'not_connected',
    account_id       TEXT NOT NULL DEFAULT '',
    account_name     TEXT NOT NULL DEFAULT '',
    page_id          TEXT NOT NULL DEFAULT '',
    page_name        TEXT NOT NULL DEFAULT '',
    scopes           TEXT NOT NULL DEFAULT '',
    issued_at        TEXT NOT NULL DEFAULT '',
    expires_at       TEXT NOT NULL DEFAULT '',
    last_validated_at TEXT NOT NULL DEFAULT '',
    activation_state TEXT NOT NULL DEFAULT 'Not configured',
    key_id           TEXT NOT NULL DEFAULT '',
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connection_tokens (
    connection_id INTEGER PRIMARY KEY,
    key_id        TEXT NOT NULL,
    nonce         TEXT NOT NULL,
    ciphertext    TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_states (
    state         TEXT PRIMARY KEY,
    provider      TEXT NOT NULL,
    code_verifier TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_flags (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
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

CREATE TABLE IF NOT EXISTS audit_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor    TEXT NOT NULL,
    action   TEXT NOT NULL,
    target   TEXT NOT NULL,
    detail   TEXT NOT NULL DEFAULT '',
    at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS request_nonces (
    nonce      TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_health (
    channel        TEXT PRIMARY KEY,
    configured     INTEGER NOT NULL DEFAULT 0,
    last_test_at   TEXT NOT NULL DEFAULT '',
    last_test_ok   INTEGER NOT NULL DEFAULT 0,
    last_digest_at TEXT NOT NULL DEFAULT '',
    detail         TEXT NOT NULL DEFAULT ''
);
