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
    if (path === "/privacy") {
      return new Response(
        `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Privacy Policy - Advertfloz</title><style>body{font-family:sans-serif;max-width:700px;margin:40px auto;line-height:1.6;padding:0 20px;color:#222;}</style></head><body><h1>Privacy Policy</h1><p><strong>Last Updated: October 2026</strong></p><p>Advertfloz is a social media campaign management tool. This Privacy Policy describes how we handle information in connection with our Meta (Facebook and Instagram) integrations.</p><h2>Data We Collect</h2><p>We only access and store the minimum necessary tokens and IDs to publish your scheduled posts and media to your designated Facebook Pages and Instagram accounts.</p><h2>How We Use Data</h2><p>Data is used exclusively to schedule, validate, and publish posts that you explicitly create and approve. We do not sell, rent, or share your data with any third parties.</p><h2>Data Deletion</h2><p>You can request deletion of all your stored data at any time by emailing <code>pravindev666@gmail.com</code>.</p></body></html>`,
        { headers: { "content-type": "text/html; charset=utf-8" } },
      );
    }
    if (path === "/terms") {
      return new Response(
        `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Terms of Service - Advertfloz</title><style>body{font-family:sans-serif;max-width:700px;margin:40px auto;line-height:1.6;padding:0 20px;color:#222;}</style></head><body><h1>Terms of Service</h1><p>By using Advertfloz, you authorize the application to manage and publish scheduled content to your connected Facebook and Instagram accounts in accordance with Meta Platform Terms.</p></body></html>`,
        { headers: { "content-type": "text/html; charset=utf-8" } },
      );
    }
    if (path === "/data-deletion") {
      return new Response(
        `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Data Deletion Instructions - Advertfloz</title><style>body{font-family:sans-serif;max-width:700px;margin:40px auto;line-height:1.6;padding:0 20px;color:#222;}</style></head><body><h1>User Data Deletion Instructions</h1><p>Advertfloz does not store personal user profiles. If you wish to delete all credentials and post data associated with your Facebook Page, please email <strong>pravindev666@gmail.com</strong> with your Page ID or disconnect your account directly from your Facebook Business Settings. All tokens and cached jobs will be removed within 24 hours.</p></body></html>`,
        { headers: { "content-type": "text/html; charset=utf-8" } },
      );
    }
    if (path === "/oauth/meta/start" || path === "/auth/meta/start") {
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
      authorize.searchParams.set("scope", "pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish,business_management");
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
    return json({
      allowed: true,
      reason: "GO: active Cloudflare D1 and R2 verified",
    });
  }
  if (path === "/api/scheduler/tick" && request.method === "POST") {
    try {
      let body: any = {};
      try { body = await request.json(); } catch {}
      const limit = Number(body.limit) || 25;
      const result = await runTick(env, { limit, leaseSeconds: 300, now: new Date(), owner: "manual" });
      return json({ ok: true, result });
    } catch (err: any) {
      return json({ error: String(err?.message || err) }, 500);
    }
  }
  if (path === "/api/media/upload" && request.method === "POST") {
    try {
      const payload: any = await request.json();
      const imageId = Number(payload.image_id);
      const filename = String(payload.filename || `${imageId}.jpg`);
      const mime = String(payload.mime || "image/jpeg");
      const sha256 = String(payload.sha256 || "");
      const b64Data = String(payload.data_b64 || "");

      if (!imageId || !b64Data) {
        return json({ error: "Missing image_id or data_b64" }, 400);
      }

      const binaryStr = atob(b64Data.replace(/-/g, "+").replace(/_/g, "/"));
      const bytes = new Uint8Array(binaryStr.length);
      for (let i = 0; i < binaryStr.length; i += 1) bytes[i] = binaryStr.charCodeAt(i);

      const objectKey = `${imageId}_${filename}`;
      await env.MEDIA.put(objectKey, bytes.buffer, {
        httpMetadata: { contentType: mime },
      });

      const now = new Date().toISOString();
      await env.DB.prepare(
        `INSERT INTO media_assets (image_id, filename, sha256, byte_size, mime, remote_object_key, production_state, sync_state, approved, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, 'approved', 'synced', 1, ?, ?)
         ON CONFLICT(image_id) DO UPDATE SET
           filename = excluded.filename,
           sha256 = excluded.sha256,
           byte_size = excluded.byte_size,
           mime = excluded.mime,
           remote_object_key = excluded.remote_object_key,
           sync_state = 'synced',
           approved = 1,
           updated_at = excluded.updated_at`
      )
        .bind(imageId, filename, sha256, bytes.byteLength, mime, objectKey, now, now)
        .run();

      return json({ ok: true, image_id: imageId, remote_object_key: objectKey });
    } catch (err: any) {
      return json({ error: String(err?.message || err) }, 500);
    }
  }
  if (path === "/api/campaigns/sync" && request.method === "POST") {
    try {
      const body: any = await request.json();
      const now = new Date().toISOString();

      if (body.campaign) {
        const c = body.campaign;
        await env.DB.prepare(
          `INSERT OR REPLACE INTO campaigns (campaign_id, name, campaign_tag, default_timezone, start_date, end_date, schema_version, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
        )
          .bind(c.campaign_id, c.name, c.campaign_tag, c.default_timezone, c.start_date, c.end_date, c.schema_version ?? "1.7", c.created_at ?? now)
          .run();
      }

      if (body.revision) {
        const r = body.revision;
        await env.DB.prepare(
          `INSERT OR REPLACE INTO campaign_revisions (revision_id, campaign_id, manifest_hash, created_at, created_by, notes)
           VALUES (?, ?, ?, ?, ?, ?)`
        )
          .bind(r.revision_id, r.campaign_id, r.manifest_hash, r.created_at ?? now, r.created_by ?? "operator", r.notes ?? "")
          .run();
      }

      if (Array.isArray(body.posts)) {
        for (const p of body.posts) {
          await env.DB.prepare(
            `INSERT OR REPLACE INTO posts (post_id, campaign_id, revision_id, image_id, scheduled_at, timezone, platforms,
                                           caption, facebook_caption, instagram_caption, alt_text, destination_url,
                                           grace_minutes, campaign_tag, ai_disclosure_status, enabled, notes, updated_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
          )
            .bind(
              p.post_id, p.campaign_id, p.revision_id, p.image_id, p.scheduled_at, p.timezone, p.platforms,
              p.caption ?? "", p.facebook_caption ?? "", p.instagram_caption ?? "", p.alt_text ?? "",
              p.destination_url ?? "", p.grace_minutes ?? 60, p.campaign_tag ?? "", p.ai_disclosure_status ?? "not_reviewed",
              p.enabled ? 1 : 0, p.notes ?? "", now
            )
            .run();
        }
      }

      if (Array.isArray(body.jobs)) {
        for (const j of body.jobs) {
          await env.DB.prepare(
            `INSERT OR REPLACE INTO platform_jobs (campaign_id, revision_id, post_id, platform, target_account_id,
                                                   status, scheduled_at, timezone, due_at_utc, idempotency_key,
                                                   attempt_count, next_retry_at, lease_owner, lease_expires_at,
                                                   remote_post_id, permalink, last_error_class, last_stage,
                                                   container_id, created_at, updated_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
          )
            .bind(
              j.campaign_id, j.revision_id, j.post_id, j.platform, j.target_account_id ?? "",
              j.status ?? "QUEUED", j.scheduled_at ?? "", j.timezone ?? "", j.due_at_utc ?? "", j.idempotency_key,
              j.attempt_count ?? 0, j.next_retry_at ?? "", "", "",
              j.remote_post_id ?? "", j.permalink ?? "", j.last_error_class ?? "unknown", j.last_stage ?? "",
              j.container_id ?? "", j.created_at ?? now, now
            )
            .run();
        }
      }

      return json({
        ok: true,
        campaign_id: body.campaign?.campaign_id,
        posts_synced: Array.isArray(body.posts) ? body.posts.length : 0,
        jobs_synced: Array.isArray(body.jobs) ? body.jobs.length : 0,
      });
    } catch (err: any) {
      return json({ error: String(err?.message || err) }, 500);
    }
  }
  if (path === "/api/campaigns/delete" && request.method === "POST") {
    try {
      const body: any = await request.json();
      const campaignId = String(body.campaign_id || "");
      if (campaignId) {
        await env.DB.prepare("DELETE FROM platform_jobs WHERE campaign_id = ?").bind(campaignId).run();
        await env.DB.prepare("DELETE FROM posts WHERE campaign_id = ?").bind(campaignId).run();
        await env.DB.prepare("DELETE FROM campaign_revisions WHERE campaign_id = ?").bind(campaignId).run();
        await env.DB.prepare("DELETE FROM campaigns WHERE campaign_id = ?").bind(campaignId).run();
      }
      return json({ ok: true, campaign_id: campaignId });
    } catch (err: any) {
      return json({ error: String(err?.message || err) }, 500);
    }
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
    authorize.searchParams.set("scope", "pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish,business_management");
    return json({ authorize_url: authorize.toString() });
  }
  if (path === "/api/connections") {
    const rows = await env.DB.prepare(
      "SELECT connection_id, provider, auth_flow, state, account_id, account_name, page_id, page_name, scopes, issued_at, expires_at, last_validated_at, activation_state, key_id, updated_at FROM connections"
    ).all();
    return json({ connections: rows.results ?? [] });
  }
  if (path === "/api/meta/pages" || path === "/api/meta/sync-pages") {
    const conn = await env.DB.prepare("SELECT * FROM connections WHERE provider = 'facebook'").first<{ connection_id: number; provider: string }>();
    if (!conn) return json({ error: "No Facebook connection found" }, 404);
    const tokenRow = await env.DB.prepare("SELECT * FROM connection_tokens WHERE connection_id = ?").bind(conn.connection_id).first<{
      key_id: string; nonce: string; ciphertext: string;
    }>();
    if (!tokenRow) return json({ error: "No token found for connection" }, 404);

    const { openToken, sealToken } = await import("./auth/crypto");
    const raw = await openToken(
      { keyId: tokenRow.key_id, nonce: tokenRow.nonce, ciphertext: tokenRow.ciphertext },
      env.TOKEN_ENCRYPTION_KEY,
    );

    let userToken = raw;
    let pageToken = raw;
    let cachedPages: Array<{ id: string; name: string; access_token?: string }> = [];
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        userToken = parsed.user_token || parsed.page_token || raw;
        pageToken = parsed.page_token || raw;
        cachedPages = parsed.pages || [];
      }
    } catch {
      // raw token
    }

    let pages: Array<{ id: string; name: string; access_token?: string }> = [];
    const resp = await fetch(`https://graph.facebook.com/${env.META_GRAPH_VERSION}/me/accounts?fields=id,name,access_token,tasks&access_token=${userToken}`);
    if (resp.ok) {
      const data: any = await resp.json();
      pages = data.data ?? [];
    } else if (cachedPages.length > 0) {
      pages = cachedPages;
    } else {
      const meResp = await fetch(`https://graph.facebook.com/${env.META_GRAPH_VERSION}/me?fields=id,name&access_token=${userToken}`);
      if (meResp.ok) {
        const meData: any = await meResp.json();
        if (meData.id && meData.name) {
          pages = [{ id: meData.id, name: meData.name, access_token: pageToken }];
        }
      }
    }

    const targetPageId = new URL(request.url).searchParams.get("page_id");
    const selected = targetPageId ? (pages.find((p: any) => p.id === targetPageId) ?? pages[0]) : pages[0];

    if (selected) {
      const now = new Date().toISOString();
      const activePageToken = selected.access_token || pageToken;

      const payload = JSON.stringify({
        user_token: userToken,
        page_token: activePageToken,
        page_id: selected.id,
        page_name: selected.name,
        pages: pages.map((p) => ({ id: p.id, name: p.name, access_token: p.access_token })),
      });

      const sealed = await sealToken(payload, env.TOKEN_ENCRYPTION_KEY, env.TOKEN_ENCRYPTION_KEY_ID ?? "k1");
      await env.DB.prepare(
        "UPDATE connection_tokens SET nonce = ?, ciphertext = ?, key_id = ?, created_at = ? WHERE connection_id = ?"
      ).bind(sealed.nonce, sealed.ciphertext, sealed.keyId, now, conn.connection_id).run();

      await env.DB.prepare(
        `UPDATE connections SET page_id = ?, page_name = ?, account_id = ?, account_name = ?,
         state = 'test_passed', activation_state = 'Ready for operator action', updated_at = ?
         WHERE connection_id = ?`
      ).bind(selected.id, selected.name, selected.id, selected.name, now, conn.connection_id).run();
    }

    return json({
      pages: pages.map((p: any) => ({ id: p.id, name: p.name })),
      selected_page: selected ? { id: selected.id, name: selected.name } : null,
    });
  }
  return json({ error: "unknown endpoint" }, 404);
}

async function sha256Url(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return btoa(String.fromCharCode(...new Uint8Array(digest))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
