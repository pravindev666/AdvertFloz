/**
 * Remote-mode Meta OAuth callback.
 *
 * This is the reachable backend for hosted deployments — Streamlit Community Cloud is never
 * assumed to be a callback backend. The code is exchanged server-side, the token is sealed with
 * the Worker secret and stored in D1, and only the browser is redirected back to the control
 * plane. No token value ever reaches the browser or the control plane.
 */
import { sealToken } from "./crypto";
import type { Env } from "../env";

const GRAPH = (env: Env, path: string) => `https://graph.facebook.com/${env.META_GRAPH_VERSION}/${path}`;

async function exchange(env: Env, code: string, verifier: string): Promise<{ payload?: any; error?: string }> {
  const params = new URLSearchParams({
    client_id: env.META_APP_ID,
    client_secret: env.META_APP_SECRET,
    redirect_uri: env.META_OAUTH_REDIRECT_URI,
    code,
  });
  if (verifier) params.set("code_verifier", verifier);

  let response = await fetch(`${GRAPH(env, "oauth/access_token")}?${params.toString()}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    const postResponse = await fetch(GRAPH(env, "oauth/access_token"), {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
      body: params.toString(),
    });
    if (postResponse.ok) {
      response = postResponse;
    }
  }

  const text = await response.text();
  try {
    const json = JSON.parse(text);
    if (json?.access_token) return { payload: json };
    const err = json?.error?.message ? `[Code ${json.error.code ?? ""}] ${json.error.message}` : text;
    return { error: err };
  } catch {
    return { error: text };
  }
}

export async function handleOAuthCallback(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const error = url.searchParams.get("error");
  const state = url.searchParams.get("state") ?? "";
  const code = url.searchParams.get("code") ?? "";

  if (error) return html(`Meta returned an error: ${error}`, 400);
  if (!state) return html("Missing OAuth state.", 400);

  const row = await env.DB.prepare("SELECT * FROM oauth_states WHERE state = ?").bind(state).first<{
    provider: string; code_verifier: string; expires_at: string;
  }>();
  // Single-use: delete regardless of outcome.
  await env.DB.prepare("DELETE FROM oauth_states WHERE state = ?").bind(state).run();
  if (!row) return html("OAuth state is invalid, expired or already used.", 400);
  if (row.expires_at <= new Date().toISOString()) return html("OAuth state expired.", 400);
  if (!code) return html("Missing authorization code.", 400);

  const token = await exchange(env, code, row.code_verifier);
  if (!token.payload) return html(`The authorization code could not be exchanged: ${token.error}`, 400);
  const data = token.payload;

  const sealed = await sealToken(data.access_token, env.TOKEN_ENCRYPTION_KEY, env.TOKEN_ENCRYPTION_KEY_ID ?? "k1");
  const now = new Date().toISOString();
  const expiresAt = data.expires_in ? new Date(Date.now() + Number(data.expires_in) * 1000).toISOString() : "";

  await env.DB.prepare(
    `INSERT INTO connections (provider, auth_flow, state, account_id, account_name, page_id, page_name, scopes,
                              issued_at, expires_at, last_validated_at, activation_state, key_id, updated_at)
     VALUES (?, 'facebook_login', 'connected_no_target', '', '', '', '', ?, ?, ?, ?, 'Needs operator action', ?, ?)
     ON CONFLICT(provider) DO UPDATE SET
       auth_flow='facebook_login', state='connected_no_target', scopes=excluded.scopes,
       issued_at=excluded.issued_at, expires_at=excluded.expires_at, last_validated_at=excluded.last_validated_at,
       key_id=excluded.key_id, updated_at=excluded.updated_at`,
  )
    .bind(row.provider, data.scope ?? "", now, expiresAt, now, sealed.keyId, now)
    .run();

  const connection = await env.DB.prepare("SELECT connection_id FROM connections WHERE provider = ?")
    .bind(row.provider)
    .first<{ connection_id: number }>();
  if (connection) {
    await env.DB.prepare(
      `INSERT INTO connection_tokens (connection_id, key_id, nonce, ciphertext, created_at) VALUES (?,?,?,?,?)
       ON CONFLICT(connection_id) DO UPDATE SET key_id=excluded.key_id, nonce=excluded.nonce,
         ciphertext=excluded.ciphertext, created_at=excluded.created_at`,
    )
      .bind(connection.connection_id, sealed.keyId, sealed.nonce, sealed.ciphertext, now)
      .run();
  }

  await env.DB.prepare("INSERT INTO audit_events (actor, action, target, detail, at) VALUES ('meta','oauth.connected',?,'callback completed',?)")
    .bind(row.provider, now)
    .run();

  return Response.redirect(env.CONTROL_PLANE_URL, 303);
}

export async function createOAuthState(env: Env, provider: string): Promise<{ state: string; verifier: string }> {
  const state = crypto.randomUUID().replace(/-/g, "");
  // Meta requires code_verifier to be 43-128 characters of [A-Za-z0-9-._~].
  // Generate 48 random bytes → 64 base64url characters.
  const buf = new Uint8Array(48);
  crypto.getRandomValues(buf);
  const verifier = btoa(String.fromCharCode(...buf)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const now = new Date();
  const expires = new Date(now.getTime() + 600_000);
  await env.DB.prepare(
    "INSERT INTO oauth_states (state, provider, code_verifier, created_at, expires_at) VALUES (?,?,?,?,?)",
  )
    .bind(state, provider, verifier, now.toISOString(), expires.toISOString())
    .run();
  return { state, verifier };
}

function html(message: string, status: number): Response {
  const safe = message.replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c] ?? c));
  return new Response(`<h3>AdvertFloz authorization failed</h3><p>${safe}</p>`, {
    status,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}
