import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("browser telemetry intake", () => {
  it("rejects cross-origin browser submissions", async () => {
    const response = await POST(
      new Request("https://app.example/api/telemetry/browser", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          origin: "https://evil.example",
          "sec-fetch-site": "cross-site",
        },
        body: JSON.stringify({
          version: 1,
          kind: "runtime_error",
          name: "window_error",
          route: "/app",
        }),
      }),
    );

    expect(response.status).toBe(403);
  });

  it("re-sanitizes accepted events before structured logging", async () => {
    const log = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const response = await POST(
      new Request("https://app.example/api/telemetry/browser", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          origin: "https://app.example",
          "sec-fetch-site": "same-origin",
        },
        body: JSON.stringify({
          version: 1,
          kind: "route_error",
          name: "react_route_error",
          route: "/app/projects/01930000-0000-7000-8000-000000000099/workspace?token=secret",
          errorCode: "route_boundary",
          requestId: "req-123",
          correlationId: "corr-123",
          prompt: "PRIVATE PROMPT",
          stack: "PRIVATE STACK",
          authorization: "Bearer private",
        }),
      }),
    );

    expect(response.status).toBe(204);
    expect(log).toHaveBeenCalledTimes(1);
    const record = String(log.mock.calls[0]?.[0]);
    expect(record).toContain('"route":"/app/projects/:id/workspace"');
    expect(record).toContain('"request_id":"req-123"');
    expect(record).toContain('"correlation_id":"corr-123"');
    expect(record).not.toContain("PRIVATE");
    expect(record).not.toContain("Bearer");
    expect(record).not.toContain("token=secret");
  });

  it("rejects oversized payloads before parsing", async () => {
    const response = await POST(
      new Request("https://app.example/api/telemetry/browser", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          origin: "https://app.example",
          "sec-fetch-site": "same-origin",
          "content-length": "9000",
        },
        body: "{}",
      }),
    );

    expect(response.status).toBe(413);
  });
});
