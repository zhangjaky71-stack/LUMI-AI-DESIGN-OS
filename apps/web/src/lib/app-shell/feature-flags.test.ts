import { describe, expect, it } from "vitest";
import { getServerPublicFeatureFlags } from "./feature-flags.server";

describe("typed public feature flags", () => {
  it("can disable a public presentation flag without exposing a mutable server security flag", () => {
    const flags = getServerPublicFeatureFlags({ LUMI_FEATURE_BILLING: "0" });
    expect(flags.billing).toBe(false);
    expect(flags.projects).toBe(true);
  });
});
