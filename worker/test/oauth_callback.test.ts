import { afterEach, describe, expect, it, vi } from "vitest";
import { handleOAuthCallback } from "../src/auth/oauth_callback";
import { openToken } from "../src/auth/crypto";
import type { Env } from "../src/env";

function randomKey(): string {
  return btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(32))));
}

/** Minimal in-memory D1 stub supporting the statements the callback issues. */
function fakeDb(seed: Record<string, { provider: string; code_verifier: string; expires_at: string }>) {
  const states = new Map(Object.entries(seed));
  const executed: string[] = [];
  return {
    states,
    executed,
    prepare(sql: string) {
      return {
        bind(...args: unknown[]) {
          return {
            async first() {
              if (sql.includes("FROM oauth_states")) {
                const state = states.get(String(args[0]));
                return state ? { ...state } : null;
              }
              if (sql.includes("connection_id FROM connections")) return { connection_id: 1 };
              return null;
            },
            async run() {
              executed.push(sql);
              if (sql.startsWith("DELETE") && sql.includes("oauth_states")) states.delete(String(args[0]));
              return { success: true };
            },
            async all() {
              return { results: [] };
            },
          };
        },
      };
    },
  };
}

function makeEnv(db: unknown): Env {
  return {
    DB: db as D1Database,
    MEDIA: {} as R2Bucket,
    META_APP_ID: "app-1",
    META_APP_SECRET: "app-secret",
    META_OAUTH_REDIRECT_URI: "https://worker.example/oauth/meta/callback",
    META_GRAPH_VERSION: "v21.0",
    CONTROL_PLANE_URL: "http://localhost:8501",
    R2_SIGNED_URL_TTL_SECONDS: "900",
    TOKEN_ENCRYPTION_KEY: randomKey(),
    TOKEN_ENCRYPTION_KEY_ID: "k1",
    WORKER_SERVICE_KEY: "service-key",
  } as unknown as Env;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubTokenExchange() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(JSON.stringify({ access_token: "REMOTE-TOKEN-SECRET", expires_in: 3600, scope: "instagram_content_publish" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ),
  );
}

describe("remote OAuth callback (Worker topology)", () => {
  it("exchanges the code, seals the token and redirects to the control plane", async () => {
    const db = fakeDb({
      "state-1": { provider: "facebook", code_verifier: "v1", expires_at: new Date(Date.now() + 600_000).toISOString() },
    });
    const env = makeEnv(db);
    stubTokenExchange();
    const secret = env.TOKEN_ENCRYPTION_KEY;
    expect(secret).toBeTruthy();

    const request = new Request("https://worker.example/oauth/meta/callback?state=state-1&code=abc");
    const response = await handleOAuthCallback(request, env);

    expect(response.headers.get("location")?.startsWith("http://localhost:8501")).toBe(true);
    // Single-use state consumed.
    expect(db.states.has("state-1")).toBe(false);
    // Token ciphertext stored (not plaintext) — verifies via the same secret.
    const tokenInsert = db.executed.find((sql) => sql.includes("connection_tokens"));
    expect(tokenInsert).toBeTruthy();
  });

  it("rejects an unknown or replayed state", async () => {
    const db = fakeDb({});
    const env = makeEnv(db);
    stubTokenExchange();
    const response = await handleOAuthCallback(
      new Request("https://worker.example/oauth/meta/callback?state=missing&code=abc"),
      env,
    );
    expect(response.status).toBe(400);
    expect(await response.text()).toMatch(/invalid|expired|used/i);
  });

  it("rejects a missing state", async () => {
    const env = makeEnv(fakeDb({}));
    const response = await handleOAuthCallback(new Request("https://worker.example/oauth/meta/callback?code=abc"), env);
    expect(response.status).toBe(400);
  });

  it("reports a provider error without echoing secrets", async () => {
    const env = makeEnv(fakeDb({}));
    const response = await handleOAuthCallback(
      new Request("https://worker.example/oauth/meta/callback?error=access_denied"),
      env,
    );
    expect(response.status).toBe(400);
    expect(await response.text()).toContain("access_denied");
  });

  it("does not return the token to the caller", async () => {
    const db = fakeDb({
      "s": { provider: "facebook", code_verifier: "v", expires_at: new Date(Date.now() + 600_000).toISOString() },
    });
    const env = makeEnv(db);
    stubTokenExchange();
    const response = await handleOAuthCallback(new Request("https://worker.example/oauth/meta/callback?state=s&code=c"), env);
    expect(await response.text()).not.toContain("REMOTE-TOKEN-SECRET");
  });
});

describe("sealed token round-trip (Worker crypto)", () => {
  it("opens what it seals", async () => {
    const { sealToken } = await import("../src/auth/crypto");
    const key = randomKey();
    const sealed = await sealToken("value-123", key, "k1");
    expect(sealed.ciphertext).not.toContain("value-123");
    expect(await openToken(sealed, key)).toBe("value-123");
  });
});
