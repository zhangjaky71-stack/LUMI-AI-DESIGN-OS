import { describe, expect, it } from "vitest";
import { formatBasisPoints, formatMicrousd, sensitiveAction } from "./contracts";


describe("NODE-64 admin contracts", () => {
  it("requires reason, ticket and exact second confirmation", () => {
    expect(() => sensitiveAction("Disable provider p", "provider:p", "reason", "INC-1", "NO")).toThrow("ADMIN_SECOND_CONFIRMATION_REQUIRED");
    expect(() => sensitiveAction("Disable provider p", "provider:p", "", "INC-1", "CONFIRM")).toThrow("ADMIN_REASON_TICKET_REQUIRED");
    expect(sensitiveAction("Disable provider p", "provider:p", "reason", "INC-1", "CONFIRM")).toEqual({
      action_summary: "Disable provider p",
      impact_scope: "provider:p",
      reason: "reason",
      ticket_ref: "INC-1",
      confirmation: "CONFIRM",
    });
  });

  it("renders service values without invented progress", () => {
    expect(formatBasisPoints(275)).toBe("2.75%");
    expect(formatMicrousd(1_500_000)).toContain("1.50");
    expect(formatMicrousd(null)).toBe("Integration pending");
  });
});
