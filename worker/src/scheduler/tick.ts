/**
 * Bounded remote scheduler tick.
 *
 * Claims a small number of due jobs with an atomic guarded UPDATE (lease), runs the pre-send
 * checks, then either dispatches, defers with backoff, marks MISSED, or records
 * UNKNOWN_OUTCOME. The Instagram create-container → check-status → publish state machine
 * advances at most one stage per tick and persists progress. This function never sleeps.
 */
import type { Env } from "../env";
import * as meta from "../meta/publish";
import { openToken } from "../auth/crypto";

export const CLAIMABLE = ["QUEUED", "PROCESSING_MEDIA"];
export const BASE_BACKOFF_SECONDS = 60;
export const MAX_BACKOFF_SECONDS = 3600;
export const IG_STAGE_DELAY_SECONDS = 30;

export interface TickOptions {
  limit: number;
  leaseSeconds: number;
  now: Date;
  owner: string;
}

export interface TickResult {
  claimed: number;
  published: number;
  deferred: number;
  missed: number;
  unknown: number;
  failedPermanent: number;
  pausedSkipped: number;
}

interface JobRow {
  job_id: number;
  campaign_id: string;
  revision_id: number;
  post_id: string;
  platform: string;
  status: string;
  scheduled_at: string;
  timezone: string;
  attempt_count: number;
  container_id: string;
  last_stage: string;
  due_at_utc: string;
}

function iso(date: Date): string {
  return date.toISOString();
}

function backoffIso(now: Date, attempt: number): string {
  const delay = Math.min(BASE_BACKOFF_SECONDS * 2 ** Math.max(0, attempt - 1), MAX_BACKOFF_SECONDS);
  const jittered = delay * (0.75 + Math.random() * 0.5);
  return iso(new Date(now.getTime() + jittered * 1000));
}

async function isPaused(env: Env, platform: string): Promise<boolean> {
  const all = await env.DB.prepare("SELECT value FROM runtime_flags WHERE key = 'pause_all'").first<{ value: string }>();
  if (all?.value === "1") return true;
  const one = await env.DB.prepare("SELECT value FROM runtime_flags WHERE key = ?")
    .bind(`pause_${platform}`)
    .first<{ value: string }>();
  return one?.value === "1";
}

/** Claim due jobs. The guarded UPDATE ensures two concurrent ticks cannot both claim a job. */
export async function claimJobs(env: Env, options: TickOptions): Promise<JobRow[]> {
  const placeholders = CLAIMABLE.map(() => "?").join(",");
  const candidates = await env.DB.prepare(
    `SELECT job_id FROM platform_jobs
      WHERE status IN (${placeholders})
        AND due_at_utc != '' AND due_at_utc <= ?
        AND (next_retry_at = '' OR next_retry_at <= ?)
        AND (lease_expires_at = '' OR lease_expires_at <= ?)
      ORDER BY due_at_utc LIMIT ?`,
  )
    .bind(...CLAIMABLE, iso(options.now), iso(options.now), iso(options.now), options.limit)
    .all<{ job_id: number }>();

  const claimed: JobRow[] = [];
  const leaseUntil = iso(new Date(options.now.getTime() + options.leaseSeconds * 1000));
  for (const row of candidates.results ?? []) {
    const update = await env.DB.prepare(
      `UPDATE platform_jobs
          SET status = 'CLAIMED', lease_owner = ?, lease_expires_at = ?, updated_at = ?
        WHERE job_id = ? AND (lease_expires_at = '' OR lease_expires_at <= ?)`,
    )
      .bind(options.owner, leaseUntil, iso(options.now), row.job_id, iso(options.now))
      .run();
    if ((update.meta?.changes ?? 0) === 1) {
      const job = await env.DB.prepare("SELECT * FROM platform_jobs WHERE job_id = ?")
        .bind(row.job_id)
        .first<JobRow>();
      if (job) claimed.push(job);
    }
  }
  return claimed;
}

async function transition(env: Env, jobId: number, status: string, fields: Record<string, string | number> = {}): Promise<void> {
  const columns = ["status = ?", "lease_owner = ''", "lease_expires_at = ''", "updated_at = ?"];
  const values: (string | number)[] = [status, iso(new Date())];
  for (const [key, value] of Object.entries(fields)) {
    columns.push(`${key} = ?`);
    values.push(value);
  }
  values.push(jobId);
  await env.DB.prepare(`UPDATE platform_jobs SET ${columns.join(", ")} WHERE job_id = ?`).bind(...values).run();
}

async function applyError(env: Env, job: JobRow, errorClass: string, summary: string): Promise<string> {
  await env.DB.prepare(
    `INSERT INTO publish_attempts (job_id, post_id, platform, stage, correlation_id, attempted_at, response_summary, error_class, retry_decision)
     VALUES (?,?,?,?,?,?,?,?,?)`,
  )
    .bind(job.job_id, job.post_id, job.platform, job.last_stage || "dispatch", "worker", iso(new Date()), summary, errorClass, errorClass)
    .run();

  if (errorClass === "auth") {
    await transition(env, job.job_id, "PAUSED", { last_error_class: errorClass });
    await env.DB.prepare(
      "INSERT OR REPLACE INTO runtime_flags (key, value, updated_at) VALUES (?, '1', ?)",
    ).bind(`pause_${job.platform}`, iso(new Date())).run();
    await raiseIncident(env, `auth-${job.job_id}`, "critical", "authorization", job, summary,
      "Reconnect the platform and re-authorize; then resume.");
    return "auth_paused";
  }
  if (errorClass === "restriction") {
    await transition(env, job.job_id, "PAUSED", { last_error_class: errorClass });
    await env.DB.prepare("INSERT OR REPLACE INTO runtime_flags (key, value, updated_at) VALUES (?, '1', ?)")
      .bind(`pause_${job.platform}`, iso(new Date())).run();
    await raiseIncident(env, `restriction-${job.job_id}`, "critical", "account_restriction", job, summary,
      "Review the account in Meta before resuming.");
    return "restricted_paused";
  }
  if (errorClass === "payload") {
    await transition(env, job.job_id, "FAILED_PERMANENT", { last_error_class: errorClass });
    return "failed_permanent";
  }
  if (errorClass === "ambiguous") {
    await transition(env, job.job_id, "UNKNOWN_OUTCOME", { last_error_class: errorClass });
    await raiseIncident(env, `unknown-${job.job_id}`, "critical", "unknown_outcome", job, summary,
      "Check the provider for this post before any retry. Do not blind retry.");
    return "unknown";
  }
  await transition(env, job.job_id, "FAILED_RETRYABLE", {
    last_error_class: errorClass,
    next_retry_at: backoffIso(new Date(), job.attempt_count + 1),
  });
  return "deferred";
}

async function raiseIncident(
  env: Env, id: string, severity: string, cause: string, job: JobRow, diagnosis: string, remediation: string,
): Promise<void> {
  await env.DB.prepare(
    `INSERT OR REPLACE INTO incidents (incident_id, severity, cause, platform, post_id, diagnosis, remediation, retry_eligible, state, created_at, acknowledged_at)
     VALUES (?,?,?,?,?,?,?,0,'open',?,'')`,
  )
    .bind(id, severity, cause, job.platform, job.post_id, diagnosis, remediation, iso(new Date()))
    .run();
}

async function resolvePlatformToken(env: Env, platform: string): Promise<string | null> {
  const provider = platform === "facebook" ? "facebook" : "instagram";
  const conn = await env.DB.prepare(
    "SELECT connection_id, state FROM connections WHERE provider = ?"
  )
    .bind(provider)
    .first<{ connection_id: number; state: string }>();

  if (!conn || (conn.state !== "ready" && conn.state !== "test_passed")) {
    return null;
  }

  const tokenRow = await env.DB.prepare(
    "SELECT key_id, nonce, ciphertext FROM connection_tokens WHERE connection_id = ?"
  )
    .bind(conn.connection_id)
    .first<{ key_id: string; nonce: string; ciphertext: string }>();

  if (!tokenRow) return null;

  try {
    const raw = await openToken(
      { keyId: tokenRow.key_id, nonce: tokenRow.nonce, ciphertext: tokenRow.ciphertext },
      env.TOKEN_ENCRYPTION_KEY,
    );
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        return parsed.page_token || parsed.user_token || raw;
      }
    } catch {
      // raw token
    }
    return raw;
  } catch (err) {
    console.error("Failed to decrypt token for", provider, err);
    return null;
  }
}

async function dispatchFacebook(env: Env, job: JobRow, result: TickResult): Promise<void> {
  const token = await resolvePlatformToken(env, "facebook");
  if (!token) {
    const label = await applyError(env, job, "auth", "missing or unreadable Facebook page access token");
    tally(result, label);
    return;
  }
  const outcome = await meta.publishFacebookPhoto(env, job, token);
  if (outcome.ok) {
    await env.DB.prepare(
      `UPDATE platform_jobs SET status='PUBLISHED', remote_post_id=?, permalink=?, attempt_count=attempt_count+1,
       lease_owner='', lease_expires_at='', updated_at=? WHERE job_id=?`,
    )
      .bind(outcome.remoteId, outcome.permalink, iso(new Date()), job.job_id)
      .run();
    result.published += 1;
  } else {
    const label = await applyError(env, job, outcome.errorClass, outcome.summary);
    tally(result, label);
  }
}

async function dispatchInstagram(env: Env, job: JobRow, result: TickResult): Promise<void> {
  const token = (await resolvePlatformToken(env, "instagram")) || (await resolvePlatformToken(env, "facebook"));
  if (!token) {
    const label = await applyError(env, job, "auth", "missing or unreadable Instagram/Facebook access token");
    tally(result, label);
    return;
  }
  const stage = job.last_stage || "CREATE_CONTAINER";
  if (stage === "CREATE_CONTAINER") {
    const created = await meta.createContainer(env, job, token);
    if (!created.ok) {
      tally(result, await applyError(env, job, created.errorClass, created.summary));
      return;
    }
    await env.DB.prepare(
      `UPDATE platform_jobs SET status='PROCESSING_MEDIA', container_id=?, last_stage='CHECK_STATUS',
       attempt_count=attempt_count+1, lease_owner='', lease_expires_at='', next_retry_at=?, updated_at=? WHERE job_id=?`,
    )
      .bind(created.containerId, iso(new Date(Date.now() + IG_STAGE_DELAY_SECONDS * 1000)), iso(new Date()), job.job_id)
      .run();
    result.deferred += 1;
    return;
  }
  if (stage === "CHECK_STATUS") {
    const status = await meta.containerStatus(env, job, token);
    if (!status.ok) {
      tally(result, await applyError(env, job, status.errorClass, status.summary));
      return;
    }
    const next = status.status === "FINISHED" ? "PUBLISH" : "CHECK_STATUS";
    await env.DB.prepare(
      `UPDATE platform_jobs SET status='PROCESSING_MEDIA', last_stage=?, lease_owner='', lease_expires_at='',
       next_retry_at=?, updated_at=? WHERE job_id=?`,
    )
      .bind(next, iso(new Date(Date.now() + IG_STAGE_DELAY_SECONDS * 1000)), iso(new Date()), job.job_id)
      .run();
    result.deferred += 1;
    return;
  }
  const published = await meta.publishContainer(env, job, token);
  if (published.ok) {
    await env.DB.prepare(
      `UPDATE platform_jobs SET status='PUBLISHED', remote_post_id=?, permalink=?, last_stage='DONE',
       attempt_count=attempt_count+1, lease_owner='', lease_expires_at='', updated_at=? WHERE job_id=?`,
    )
      .bind(published.remoteId, published.permalink, iso(new Date()), job.job_id)
      .run();
    result.published += 1;
  } else {
    tally(result, await applyError(env, job, published.errorClass, published.summary));
  }
}

function tally(result: TickResult, label: string): void {
  if (label === "unknown") result.unknown += 1;
  else if (label === "failed_permanent") result.failedPermanent += 1;
  else result.deferred += 1;
}

export async function runTick(env: Env, options: TickOptions): Promise<TickResult> {
  const result: TickResult = {
    claimed: 0, published: 0, deferred: 0, missed: 0, unknown: 0, failedPermanent: 0, pausedSkipped: 0,
  };
  const jobs = await claimJobs(env, options);
  result.claimed = jobs.length;

  for (const job of jobs) {
    const post = await env.DB.prepare(
      "SELECT * FROM posts WHERE campaign_id = ? AND revision_id = ? AND post_id = ?",
    )
      .bind(job.campaign_id, job.revision_id, job.post_id)
      .first<{ image_id: number; scheduled_at: string; grace_minutes: number | null }>();
    if (!post) {
      await transition(env, job.job_id, "FAILED_PERMANENT", { last_error_class: "payload" });
      result.failedPermanent += 1;
      continue;
    }
    if (await isPaused(env, job.platform)) {
      await transition(env, job.job_id, "QUEUED");
      result.pausedSkipped += 1;
      continue;
    }
    if (job.platform === "facebook") await dispatchFacebook(env, job, result);
    else await dispatchInstagram(env, job, result);
  }

  await env.DB.prepare("INSERT OR REPLACE INTO runtime_flags (key, value, updated_at) VALUES ('worker_heartbeat_at', ?, ?)")
    .bind(iso(options.now), iso(options.now))
    .run();
  return result;
}
