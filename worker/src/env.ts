/** Worker bindings and configuration. */
export interface Env {
  DB: D1Database;
  MEDIA: R2Bucket;
  META_GRAPH_VERSION: string;
  META_APP_ID: string;
  META_OAUTH_REDIRECT_URI: string;
  CONTROL_PLANE_URL: string;
  R2_SIGNED_URL_TTL_SECONDS: string;

  // Secrets — set with `wrangler secret put`, never committed.
  META_APP_SECRET: string;
  TOKEN_ENCRYPTION_KEY: string; // base64 32-byte key; kept separate from stored ciphertext
  TOKEN_ENCRYPTION_KEY_ID?: string;
  WORKER_SERVICE_KEY: string;
  TELEGRAM_BOT_TOKEN?: string;
  TELEGRAM_ALLOWED_CHAT_ID?: string;
  TELEGRAM_WEBHOOK_SECRET?: string;
}

export const SIGNATURE_HEADER = "x-advertfloz-signature";
export const TIMESTAMP_HEADER = "x-advertfloz-timestamp";
export const NONCE_HEADER = "x-advertfloz-nonce";

/** Reject requests whose timestamp is outside this window (replay protection). */
export const MAX_CLOCK_SKEW_SECONDS = 300;
