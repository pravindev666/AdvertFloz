import { describe, expect, it } from "vitest";
import { signRequest, verifyServiceRequest } from "../src/auth/service_auth";
import { openToken, sealToken } from "../src/auth/crypto";
import type { Env } from "../src/env";

/** Minimal in-memory D1 stub supporting the queries service_auth uses. */
function fakeDb() {
  const nonces = new Set<string>();
  return {
    prepare(sql: string) {
      return {
        bind(...args: unknown[]) {
          return {
            async first() {
              if (sql.includes("FROM request_nonces")) {
                return nonces.has(String(args[0])) ? { nonce: args[0] } : null;
              }
              return null;
            },
            async run() {
              if (sql.includes("INSERT INTO request_nonces")) nonces.add(String(args[0]));
              return { success: true };
            },
          };
        },
      };
    },
  } as unknown as D1Database;
}

function env(): Env {
  return {
    WORKER_SERVICE_KEY: "service-key",
    DB: fakeDb(),
  } as unknown as Env;
}

describe("service auth", () => {
  it("accepts a correctly signed request", async () => {
    const e = env();
    const headers = await signRequest("service-key", "POST", "/api/control/pause", "{}");
    const request = new Request("https://w.example/api/control/pause", { method: "POST", headers, body: "{}" });
    expect((await verifyServiceRequest(request, e, "{}")).ok).toBe(true);
  });

  it("rejects a bad signature", async () => {
    const e = env();
    const headers = await signRequest("wrong-key", "POST", "/api/control/pause", "{}");
    const request = new Request("https://w.example/api/control/pause", { method: "POST", headers, body: "{}" });
    const result = await verifyServiceRequest(request, e, "{}");
    expect(result.ok).toBe(false);
    expect(result.status).toBe(401);
  });

  it("rejects a replayed nonce", async () => {
    const e = env();
    const headers = await signRequest("service-key", "GET", "/api/status", "");
    const make = () => new Request("https://w.example/api/status", { method: "GET", headers });
    expect((await verifyServiceRequest(make(), e, "")).ok).toBe(true);
    const second = await verifyServiceRequest(make(), e, "");
    expect(second.ok).toBe(false);
    expect(second.status).toBe(409);
  });

  it("rejects a stale timestamp", async () => {
    const e = env();
    const headers = await signRequest("service-key", "GET", "/api/status", "", "1000000");
    const request = new Request("https://w.example/api/status", { method: "GET", headers });
    expect((await verifyServiceRequest(request, e, "")).ok).toBe(false);
  });
});

describe("token sealing", () => {
  it("round-trips and does not store plaintext", async () => {
    const key = btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(32))));
    const sealed = await sealToken("super-secret", key, "k1");
    expect(sealed.keyId).toBe("k1");
    expect(sealed.ciphertext).not.toContain("super-secret");
    expect(await openToken(sealed, key)).toBe("super-secret");
  });
});
