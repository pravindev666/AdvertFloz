/** Telegram command channel for the remote plane. Allow-listed chat id only. */
import type { Env } from "../env";

const ALLOWED = new Set([
  "/status",
  "/pause", "/pause facebook", "/pause instagram", "/pause all",
  "/resume", "/resume facebook", "/resume instagram", "/resume all",
]);

export async function handleTelegramCommand(request: Request, env: Env): Promise<Response> {
  const secret = request.headers.get("x-telegram-bot-api-secret-token") ?? "";
  if (!env.TELEGRAM_WEBHOOK_SECRET || secret !== env.TELEGRAM_WEBHOOK_SECRET) {
    return new Response("forbidden", { status: 403 });
  }
  const update = await request.json<any>().catch(() => null);
  const chatId = String(update?.message?.chat?.id ?? "");
  const text = String(update?.message?.text ?? "").trim().toLowerCase().replace(/\s+/g, " ");

  if (!env.TELEGRAM_ALLOWED_CHAT_ID || chatId !== env.TELEGRAM_ALLOWED_CHAT_ID) {
    return new Response("unauthorized", { status: 200 }); // 200 so Telegram doesn't retry
  }
  if (!ALLOWED.has(text)) return new Response("unsupported", { status: 200 });

  const now = new Date().toISOString();
  if (text === "/status") {
    const counts = await env.DB.prepare("SELECT status, COUNT(*) AS n FROM platform_jobs GROUP BY status").all();
    return reply(env, `AdvertFloz status: ${JSON.stringify(counts.results ?? [])}`);
  }
  const parts = text.split(" ");
  const verb = parts[0].replace("/", "");
  const target = parts[1] ?? "all";
  const key = target === "all" ? "pause_all" : `pause_${target}`;
  const value = verb === "pause" ? "1" : "0";
  await env.DB.prepare("INSERT OR REPLACE INTO runtime_flags (key, value, updated_at) VALUES (?,?,?)")
    .bind(key, value, now)
    .run();
  await env.DB.prepare("INSERT INTO audit_events (actor, action, target, detail, at) VALUES ('telegram',?,?,?,?)")
    .bind(verb, target, "telegram command", now)
    .run()
    .catch(() => undefined);
  return reply(env, `${verb} ${target} recorded. An in-flight call cannot be recalled.`);
}

async function reply(env: Env, text: string): Promise<Response> {
  if (env.TELEGRAM_BOT_TOKEN && env.TELEGRAM_ALLOWED_CHAT_ID) {
    await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ chat_id: env.TELEGRAM_ALLOWED_CHAT_ID, text }),
    }).catch(() => undefined);
  }
  return new Response("ok", { status: 200 });
}
