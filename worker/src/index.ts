/** Worker entry point: HTTP router + bounded scheduled handler. */
import { handleOAuthCallback } from "./auth/oauth_callback";
import { verifyServiceRequest } from "./auth/service_auth";
import type { Env } from "./env";
import { serveMedia } from "./media/r2";
import { runTick } from "./scheduler/tick";
import { handleTelegramCommand } from "./notifications/telegram";

const SECURITY_HEADERS: Record<string, string> = {
  "x-content-type-options": "nosniff",
  "referrer-policy": "no-referrer",
  "cache-control": "no-store",
};

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json", ...SECURITY_HEADERS },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === "/health") return json({ status: "ok", service: "advertfloz-worker" });
    if (path === "/oauth/meta/start") {
      const provider = url.searchParams.get("provider") ?? "facebook";
      const { createOAuthState } = await import("./auth/oauth_callback");
      const { state, verifier } = await createOAuthState(env, provider);
      const challenge = await sha256Url(verifier);
      const authorize = new URL(`https://www.facebook.com/${env.META_GRAPH_VERSION}/dialog/oauth`);
      authorize.searchParams.set("client_id", env.META_APP_ID);
      authorize.searchParams.set("redirect_uri", env.META_OAUTH_REDIRECT_URI);
      authorize.searchParams.set("state", state);
      authorize.searchParams.set("code_challenge", challenge);
      authorize.searchParams.set("code_challenge_method", "S256");
      authorize.searchParams.set("response_type", "code");
      authorize.searchParams.set("scope", "pages_show_list,pages_manage_posts,instagram_content_publish,business_management");
      return Response.redirect(authorize.toString(), 302);
    }
    if (path === "/oauth/meta/callback") return handleOAuthCallback(request, env);
    if (path.startsWith("/media/")) {
      const key = decodeURIComponent(path.slice("/media/".length));
      return serveMedia(env, key, url.searchParams.get("expires") ?? "", url.searchParams.get("signature") ?? "");
    }
    if (path === "/telegram/webhook" && request.method === "POST") {
      return handleTelegramCommand(request, env);
    }
    if (path.startsWith("/api/")) {
      const body = request.method === "GET" ? "" : await request.clone().text();
      const auth = await verifyServiceRequest(request, env, body);
      if (!auth.ok) return json({ error: auth.reason }, auth.status ?? 401);
      return handleApi(request, env, path);
    }
    return json({ error: "not found" }, 404);
  },

  async scheduled(_event: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(
      runTick(env, { limit: 5, leaseSeconds: 300, now: new Date(), owner: "cron" }).then(async (result) => {
        await env.DB.prepare("INSERT INTO audit_events (actor, action, target, detail, at) VALUES ('cron','tick','worker',?,?)")
          .bind(JSON.stringify(result), new Date().toISOString())
          .run();
      }),
    );
  },
};

async function handleApi(request: Request, env: Env, path: string): Promise<Response> {
  if (path === "/api/status") {
    const counts = await env.DB.prepare("SELECT status, COUNT(*) AS n FROM platform_jobs GROUP BY status").all();
    const heartbeat = await env.DB.prepare("SELECT value FROM runtime_flags WHERE key='worker_heartbeat_at'").first();
    return json({ counts: counts.results ?? [], heartbeat: heartbeat?.value ?? null });
  }
  if (path === "/api/jobs") {
    const rows = await env.DB.prepare("SELECT * FROM platform_jobs ORDER BY due_at_utc LIMIT 500").all();
    return json({ jobs: rows.results ?? [] });
  }
  if (path === "/api/cost-gate") {
    // The gate is authoritative here too: remote stays disabled until prerequisites pass.
    return json({
      allowed: false,
      reason: "NO-GO until R2 payment prerequisite, quotas, media retrieval, auth and restore are verified on the real account",
    });
  }
  if (path === "/api/control/pause" || path === "/api/control/resume") {
    const target = new URL(request.url).searchParams.get("target") ?? "all";
    const key = target === "all" ? "pause_all" : `pause_${target}`;
    const value = path.endsWith("pause") ? "1" : "0";
    await env.DB.prepare("INSERT OR REPLACE INTO runtime_flags (key, value, updated_at) VALUES (?,?,?)")
      .bind(key, value, new Date().toISOString())
      .run();
    await env.DB.prepare("INSERT INTO audit_events (actor, action, target, detail, at) VALUES ('api',?,?,'','')")
      .bind(path.endsWith("pause") ? "pause" : "resume", target)
      .run()
      .catch(() => undefined);
    return json({ ok: true, target, paused: value === "1" });
  }
  if (path === "/api/oauth/start") {
    const provider = new URL(request.url).searchParams.get("provider") ?? "facebook";
    const { createOAuthState } = await import("./auth/oauth_callback");
    const { state, verifier } = await createOAuthState(env, provider);
    const challenge = await sha256Url(verifier);
    const authorize = new URL(`https://www.facebook.com/${env.META_GRAPH_VERSION}/dialog/oauth`);
    authorize.searchParams.set("client_id", env.META_APP_ID);
    authorize.searchParams.set("redirect_uri", env.META_OAUTH_REDIRECT_URI);
    authorize.searchParams.set("state", state);
    authorize.searchParams.set("code_challenge", challenge);
    authorize.searchParams.set("code_challenge_method", "S256");
    authorize.searchParams.set("response_type", "code");
    authorize.searchParams.set("scope", "pages_show_list,pages_manage_posts,instagram_content_publish,business_management");
    return json({ authorize_url: authorize.toString() });
  }
  return json({ error: "unknown endpoint" }, 404);
}

async function sha256Url(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return btoa(String.fromCharCode(...new Uint8Array(digest))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
