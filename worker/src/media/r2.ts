/**
 * Private media storage on R2 with short-lived signed URLs.
 *
 * The bucket stays private: Meta fetches media through this Worker route, which only serves an
 * object when the HMAC signature and expiry are valid. Media is only uploaded here after the
 * zero-cost gate passes.
 */
import type { Env } from "../env";

export const MEDIA_TTL_SECONDS = 900;
export const MEDIA_PATH = "/media";

async function hmacHex(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function origin(env: Env): string {
  // Prefer the Worker domain derived from the configured OAuth callback.
  try {
    return new URL(env.META_OAUTH_REDIRECT_URI).origin;
  } catch {
    return "https://REPLACE_WITH_WORKER_DOMAIN";
  }
}

export async function signMediaKey(env: Env, objectKey: string, ttlSeconds = MEDIA_TTL_SECONDS): Promise<string> {
  const expires = Math.floor(Date.now() / 1000) + ttlSeconds;
  const signature = await hmacHex(env.WORKER_SERVICE_KEY, `${objectKey}:${expires}`);
  return `${origin(env)}${MEDIA_PATH}/${objectKey}?expires=${expires}&signature=${signature}`;
}

export async function verifyMediaRequest(env: Env, objectKey: string, expires: string, signature: string): Promise<boolean> {
  const expiry = Number(expires);
  if (!Number.isFinite(expiry) || expiry < Math.floor(Date.now() / 1000)) return false;
  const expected = await hmacHex(env.WORKER_SERVICE_KEY, `${objectKey}:${expiry}`);
  if (expected.length !== signature.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i += 1) diff |= expected.charCodeAt(i) ^ signature.charCodeAt(i);
  return diff === 0;
}

export async function mediaUrlFor(env: Env, imageId: number, campaignId?: string): Promise<string> {
  // 1. Try campaign-scoped lookup first
  if (campaignId) {
    try {
      const campRow = await env.DB.prepare(
        "SELECT remote_object_key FROM campaign_media WHERE campaign_id = ? AND image_id = ?"
      )
        .bind(campaignId, imageId)
        .first<{ remote_object_key: string }>();
      if (campRow?.remote_object_key) {
        return signMediaKey(env, campRow.remote_object_key);
      }
    } catch {
      // Table may not exist yet on legacy setups
    }
  }

  // 2. Fall back to global media_assets table
  try {
    const row = await env.DB.prepare("SELECT remote_object_key FROM media_assets WHERE image_id = ?")
      .bind(imageId)
      .first<{ remote_object_key: string }>();
    if (row?.remote_object_key) {
      return signMediaKey(env, row.remote_object_key);
    }
  } catch {
    // DB lookup error
  }

  // 3. Fall back to conventional campaign path if campaignId provided
  if (campaignId) {
    return signMediaKey(env, `${campaignId}/${imageId}_${imageId}.jpg`);
  }

  return "";
}

export async function serveMedia(env: Env, objectKey: string, expires: string, signature: string): Promise<Response> {
  if (!(await verifyMediaRequest(env, objectKey, expires, signature))) {
    return new Response("forbidden", { status: 403 });
  }
  const object = await env.MEDIA.get(objectKey);
  if (!object) return new Response("not found", { status: 404 });
  return new Response(object.body, {
    headers: {
      "content-type": object.httpMetadata?.contentType ?? "image/jpeg",
      "cache-control": "private, max-age=300",
    },
  });
}
