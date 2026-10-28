-- Migration 0002: Campaign-scoped media storage
-- Allows multiple campaigns to reuse image IDs (1.jpg..30.jpg) without collisions or overwrites.

CREATE TABLE IF NOT EXISTS campaign_media (
    campaign_id       TEXT NOT NULL,
    image_id          INTEGER NOT NULL,
    filename          TEXT NOT NULL,
    remote_object_key TEXT NOT NULL,
    sha256            TEXT NOT NULL DEFAULT '',
    byte_size         INTEGER NOT NULL DEFAULT 0,
    mime              TEXT NOT NULL DEFAULT 'image/jpeg',
    created_at        TEXT NOT NULL,
    PRIMARY KEY (campaign_id, image_id)
);

CREATE INDEX IF NOT EXISTS idx_campaign_media_lookup
    ON campaign_media (campaign_id, image_id);
