/**
 * Meta Graph publishing for the remote plane. Uses only official endpoints. Every response is
 * classified so the scheduler can decide retry vs pause vs reconcile.
 */
import type { Env } from "../env";
import { mediaUrlFor } from "../media/r2";

export interface Outcome {
  ok: boolean;
  remoteId: string;
  permalink: string;
  errorClass: string;
  summary: string;
}

const OK: Outcome = { ok: true, remoteId: "", permalink: "", errorClass: "unknown", summary: "" };

export function classify(status: number, payload: any): string {
  const code = payload?.error?.code;
  const message = String(payload?.error?.message ?? "").toLowerCase();
  if ([190, 102, 463, 467].includes(code) || message.includes("access token")) return "auth";
  if ([10, 200, 202].includes(code)) return "auth";
  if ([368, 131000, 131031].includes(code) || message.includes("restricted")) return "restriction";
  if ([4, 17, 32, 613].includes(code) || status === 429) return "rate_limit";
  if ([100, 324, 352].includes(code) || [400, 415, 422].includes(status)) return "payload";
  if (status >= 500 || status === 408 || status === 504) return "transient";
  return "unknown";
}

async function call(env: Env, method: "GET" | "POST", path: string, token: string, body?: Record<string, string>): Promise<Outcome> {
  const url = new URL(`https://graph.facebook.com/${env.META_GRAPH_VERSION}/${path.replace(/^\//, "")}`);
  const init: RequestInit = { method, headers: {} };
  if (method === "GET") {
    for (const [k, v] of Object.entries(body ?? {})) url.searchParams.set(k, v);
    url.searchParams.set("access_token", token);
  } else {
    const form = new URLSearchParams({ ...(body ?? {}), access_token: token });
    init.body = form.toString();
    init.headers = { "content-type": "application/x-www-form-urlencoded" };
  }
  let response: Response;
  try {
    response = await fetch(url.toString(), init);
  } catch {
    // Network failure before a response: safe to retry.
    return { ok: false, remoteId: "", permalink: "", errorClass: "transient", summary: "transport error before response" };
  }
  let payload: any = {};
  try {
    payload = await response.json();
  } catch {
    return { ok: false, remoteId: "", permalink: "", errorClass: "unknown", summary: `non-JSON response status=${response.status}` };
  }
  if (!response.ok || payload?.error) {
    return {
      ok: false, remoteId: "", permalink: "",
      errorClass: classify(response.status, payload),
      summary: `status=${response.status} code=${payload?.error?.code ?? ""}`,
    };
  }
  return { ...OK, remoteId: payload.id ?? payload.post_id ?? "", permalink: payload.permalink ?? "" };
}

interface JobLike {
  post_id: string;
  campaign_id: string;
  revision_id: number;
  platform: string;
  container_id?: string;
}

async function pageAndIgTargets(env: Env, job: JobLike): Promise<{ pageId: string; igId: string; caption: string; imageId: number }> {
  const post = await env.DB.prepare(
    "SELECT image_id, caption, facebook_caption, instagram_caption FROM posts WHERE campaign_id=? AND revision_id=? AND post_id=?",
  )
    .bind(job.campaign_id, job.revision_id, job.post_id)
    .first<{ image_id: number; caption: string; facebook_caption: string; instagram_caption: string }>();
  const caption = job.platform === "facebook"
    ? post?.facebook_caption || post?.caption || ""
    : post?.instagram_caption || post?.caption || "";
  const fb = await env.DB.prepare("SELECT page_id FROM connections WHERE provider='facebook'").first<{ page_id: string }>();
  const ig = await env.DB.prepare("SELECT account_id FROM connections WHERE provider='instagram'").first<{ account_id: string }>();
  return { pageId: fb?.page_id ?? "", igId: ig?.account_id ?? "", caption, imageId: post?.image_id ?? 0 };
}

export async function publishFacebookPhoto(env: Env, job: JobLike, token: string): Promise<Outcome> {
  const { pageId, caption, imageId } = await pageAndIgTargets(env, job);
  const mediaUrl = await mediaUrlFor(env, imageId);
  if (!pageId || !mediaUrl) {
    return { ok: false, remoteId: "", permalink: "", errorClass: "auth", summary: "missing page target or media URL" };
  }
  // Meta Graph API requires 'message' for the text to appear in the Facebook Timeline feed stream.
  return call(env, "POST", `${pageId}/photos`, token, {
    url: mediaUrl,
    message: caption,
    caption: caption,
    published: "true",
  });
}

export async function createContainer(env: Env, job: JobLike, token: string): Promise<Outcome & { containerId: string }> {
  const { igId, caption, imageId } = await pageAndIgTargets(env, job);
  const mediaUrl = await mediaUrlFor(env, imageId);
  if (!igId || !mediaUrl) {
    return { ok: false, containerId: "", remoteId: "", permalink: "", errorClass: "auth", summary: "missing IG target or media URL" };
  }
  const outcome = await call(env, "POST", `${igId}/media`, token, { image_url: mediaUrl, caption });
  return { ...outcome, containerId: outcome.remoteId };
}

export async function containerStatus(env: Env, job: JobLike, token: string): Promise<Outcome & { status: string }> {
  const outcome = await call(env, "GET", `${job.container_id}`, token, { fields: "status_code" });
  return { ...outcome, status: outcome.ok ? "IN_PROGRESS" : "ERROR" };
}

export async function publishContainer(env: Env, job: JobLike, token: string): Promise<Outcome> {
  const { igId } = await pageAndIgTargets(env, job);
  return call(env, "POST", `${igId}/media_publish`, token, { creation_id: job.container_id ?? "" });
}
