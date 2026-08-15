import { describe, expect, it } from "vitest";
import { LumiApiClient, LumiApiError } from "./api-client";

function response(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

describe("LumiApiClient", () => {
  it("surfaces stable Problem Details codes instead of parsing messages", async () => {
    const transport: typeof fetch = async () =>
      response(
        {
          type: "https://errors.lumi.dev/project/not-found",
          title: "Project not found",
          status: 404,
          code: "PROJECT_NOT_FOUND",
          request_id: "req-server",
        },
        404,
      );
    const client = new LumiApiClient({
      base_url: "https://api.test/v1",
      transport,
    });

    try {
      await client.get("/projects/missing");
      throw new Error("expected request to fail");
    } catch (error) {
      expect(error).toBeInstanceOf(LumiApiError);
      expect((error as LumiApiError).problem.code).toBe("PROJECT_NOT_FOUND");
      expect((error as LumiApiError).problem.request_id).toBe("req-server");
    }
  });

  it("retries only safe GET requests", async () => {
    let calls = 0;
    const transport: typeof fetch = async () => {
      calls += 1;
      return calls < 3
        ? response({ code: "TEMP" }, 503)
        : response({ items: ["ok"] });
    };
    const client = new LumiApiClient({
      base_url: "https://api.test/v1",
      transport,
    });

    await expect(
      client.get<{ items: string[] }>("/projects"),
    ).resolves.toEqual({ items: ["ok"] });
    expect(calls).toBe(3);
  });

  it("never retries a mutation after a transient response", async () => {
    let calls = 0;
    const transport: typeof fetch = async () => {
      calls += 1;
      return response({ code: "TEMP" }, 503);
    };
    const client = new LumiApiClient({
      base_url: "https://api.test/v1",
      transport,
    });

    await expect(
      client.post("/projects", { title: "Poster" }, { idempotency_key: "i-1" }),
    ).rejects.toBeInstanceOf(LumiApiError);
    expect(calls).toBe(1);
  });

  it("adds tenant, csrf, idempotency and concurrency headers to mutations", async () => {
    let calls = 0;
    let captured = new Headers();
    const transport: typeof fetch = async (_input, init) => {
      calls += 1;
      captured = new Headers(init?.headers);
      return response({ ok: true });
    };
    const client = new LumiApiClient({
      base_url: "https://api.test/v1",
      transport,
      context: () => ({
        organization_id: "org-1",
        csrf_token: "csrf-test",
      }),
    });

    await client.post(
      "/projects",
      { title: "Poster" },
      { idempotency_key: "idem-1", if_match: "v7" },
    );
    expect(calls).toBe(1);
    expect(captured.get("x-lumi-organization-id")).toBe("org-1");
    expect(captured.get("x-csrf-token")).toBe("csrf-test");
    expect(captured.get("idempotency-key")).toBe("idem-1");
    expect(captured.get("if-match")).toBe("v7");
  });
});
