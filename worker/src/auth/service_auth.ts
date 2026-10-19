/**
 * Service-to-service authentication for the remote plane.
 *
 * Every request from the control plane carries a bearer service key, a timestamp and a
 * single-use nonce, plus an HMAC signature over method+path+timestamp+nonce+body. Nonces are
 * persisted so a replay is rejected. The bearer key can be rotated (two keys accepted during
 * a rotation window).
 */
import type { Env } from "../env";
import { MAX_CLOCK_SKEW_SECONDS, NONCE_HEADER, SIGNATURE_HEADER, TIMESTAMP_HEADER } from "../env";

export interface AuthResult {
  ok: boolean
  status?: number;
  reason?: string;
}

async function hmacHex(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return [...new Uint8Array(signature)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function verifyServiceRequest(request: Request, env: Env, body: string): Promise<AuthResult> {
  const auth = request.headers.get("authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return { ok: false, status: 401, reason: "missing bearer token" };
  const presented = auth.slice("Bearer ".length);
  const accepted = [env.WORKER_SERVICE_KEY, (env as unknown as Record<string, string>).WORKER_SERVICE_KEY_PREVIOUS]
    .filter(Boolean);
  if (!accepted.some((key) => timingSafeEqual(key, presented))) {
    return { ok: false, status: 401, reason: "invalid service key" };
  }

  const timestamp = request.headers.get(TIMESTAMP_HEADER) ?? "";
  const nonce = request.headers.get(NONCE_HEADER) ?? "";
  const signature = request.headers.get(SIGNATURE_HEADER) ?? "";
  if (!timestamp || !nonce || !signature) return { ok: false, status: 401, reason: "missing signature headers" };

  const skew = Math.abs(Date.now() / 1000 - Number(timestamp));
  if (!Number.isFinite(skew) || skew > MAX_CLOCK_SKEW_SECONDS) {
    return { ok: false, status: 401, reason: "timestamp outside the allowed window" };
  }

  const url = new URL(request.url);
  const expected = await hmacHex(env.WORKER_SERVICE_KEY, `${request.method}\n${url.pathname}\n${timestamp}\n${nonce}\n${body}`);
  if (!timingSafeEqual(expected, signature)) return { ok: false, status: 401, reason: "signature mismatch" };

  // Single-use nonce (replay protection).
  const existing = await env.DB.prepare("SELECT nonce FROM request_nonces WHERE nonce = ?").bind(nonce).first();
  if (existing) return { ok: false, status: 409, reason: "replayed nonce" };
  await env.DB.prepare("INSERT INTO request_nonces (nonce, created_at) VALUES (?, ?)")
    .bind(nonce, new Date().toISOString())
    .run();
  return { ok: true };
}

export async function signRequest(
  secret: string,
  method: string,
  path: string,
  body: string,
  timestamp = Math.floor(Date.now() / 1000).toString(),
  nonce = crypto.randomUUID().replace(/-/g, ""),
): Promise<Record<string, string>> {
  const signature = await hmacHex(secret, `${method}\n${path}\n${timestamp}\n${nonce}\n${body}`);
  return {
    authorization: `Bearer ${secret}`,
    [TIMESTAMP_HEADER]: timestamp,
    [NONCE_HEADER]: nonce,
    [SIGNATURE_HEADER]: signature,
  };
}
