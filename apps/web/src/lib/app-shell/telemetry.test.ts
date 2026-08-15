import { describe, expect, it } from "vitest";
import { sanitizeTelemetryProperties } from "./telemetry";

describe("telemetry privacy boundary", () => {
  it("allows aggregate product metadata", () => {
    expect(sanitizeTelemetryProperties({ path: "/app/projects", organization_id: "org-1", count: 2 })).toEqual({
      path: "/app/projects",
      organization_id: "org-1",
      count: 2,
    });
  });

  it.each(["prompt", "image_url", "authorization_token", "email"])("rejects sensitive property %s", (key) => {
    expect(() => sanitizeTelemetryProperties({ [key]: "secret-value" })).toThrow("TELEMETRY_SENSITIVE_PROPERTY_FORBIDDEN");
  });
});
