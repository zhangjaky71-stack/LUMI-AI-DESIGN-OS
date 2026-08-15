import { describe, expect, it } from "vitest";

import {
  normalizeTelemetryRoute,
  safeTelemetryRef,
  sanitizeBrowserTelemetry,
} from "./browser";

describe("browser observability privacy contract", () => {
  it("normalizes identifiers and strips query/hash from routes", () => {
    expect(
      normalizeTelemetryRoute(
        "https://app.example/app/projects/01930000-0000-7000-8000-000000000099/workspace?token=secret#x",
      ),
    ).toBe("/app/projects/:id/workspace");
    expect(normalizeTelemetryRoute("/api/v1/assets/123456789/download?signed=secret")).toBe(
      "/api/v1/assets/:id/download",
    );
  });

  it("rejects unsafe correlation identifiers", () => {
    expect(safeTelemetryRef("req-123")).toBe("req-123");
    expect(safeTelemetryRef("Bearer secret value")).toBeUndefined();
    expect(safeTelemetryRef("x".repeat(129))).toBeUndefined();
  });

  it("drops unknown content fields instead of forwarding user data", () => {
    const event = sanitizeBrowserTelemetry({
      version: 1,
      kind: "route_error",
      name: "react_route_error",
      route: "/app/projects/01930000-0000-7000-8000-000000000099/workspace?prompt=secret",
      errorCode: "route_boundary",
      prompt: "PRIVATE PROMPT",
      stack: "PRIVATE STACK",
      message: "PRIVATE MESSAGE",
      canvas: "PRIVATE CANVAS",
      authorization: "Bearer secret",
    });

    expect(event).toEqual({
      version: 1,
      kind: "route_error",
      name: "react_route_error",
      route: "/app/projects/:id/workspace",
      errorCode: "route_boundary",
    });
    expect(JSON.stringify(event)).not.toContain("PRIVATE");
    expect(JSON.stringify(event)).not.toContain("Bearer");
  });

  it("bounds metric values and status dimensions", () => {
    expect(
      sanitizeBrowserTelemetry({
        version: 1,
        kind: "web_vital",
        name: "lcp_ms",
        route: "/app",
        value: Number.POSITIVE_INFINITY,
        statusClass: "404",
      }),
    ).toEqual({
      version: 1,
      kind: "web_vital",
      name: "lcp_ms",
      route: "/app",
    });

    expect(
      sanitizeBrowserTelemetry({
        version: 1,
        kind: "api_failure",
        name: "api_get_failed",
        route: "/api/v1/projects/123456789",
        statusClass: "5xx",
        value: 999_999_999,
      }),
    ).toEqual({
      version: 1,
      kind: "api_failure",
      name: "api_get_failed",
      route: "/api/v1/projects/:id",
      statusClass: "5xx",
      value: 86_400_000,
    });
  });

  it("rejects unknown event kinds and free-form names", () => {
    expect(
      sanitizeBrowserTelemetry({ version: 1, kind: "prompt", name: "x", route: "/" }),
    ).toBeNull();
    expect(
      sanitizeBrowserTelemetry({
        version: 1,
        kind: "runtime_error",
        name: "User said their secret prompt",
        route: "/",
      }),
    ).toBeNull();
  });
});
