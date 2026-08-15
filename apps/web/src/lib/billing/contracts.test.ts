import { describe, expect, it } from "vitest";
import { creditUsagePercent, formatMicrousd, planLabel, safeHttpsBillingUrl, subscriptionKeepsEntitlements } from "./contracts";
import type { BillingWorkspace } from "./types";

const workspace: BillingWorkspace = {
  organization_id: "org-1",
  current_plan: { plan_id: "pro", plan_version_id: "pro-v2", version: 2, name: "Pro", currency: "USD", price_microusd: 49_000_000, billing_interval: "MONTH", monthly_credit_grant: 1000, entitlements: {}, status: "ACTIVE" },
  subscription: { subscription_id: "sub-1", organization_id: "org-1", plan_version_id: "pro-v2", payment_provider: "MOCK", provider_subscription_ref: "mock-sub", state: "ACTIVE", current_period_start: null, current_period_end: null, cancel_at_period_end: false },
  plans: [], credit_balance: 750, credit_entries: [], invoices: [], entitlements: {}, can_manage: true, payment_provider: "MOCK", provider_cost_reconciliation_available: false,
};

describe("NODE-63 billing contracts", () => {
  it("formats microusd without using display math as billing truth", () => expect(formatMicrousd(49_000_000)).toContain("49.00"));
  it("rejects unsafe microusd display values", () => expect(formatMicrousd(Number.MAX_SAFE_INTEGER + 1)).toBe("—"));
  it("shows immutable plan version", () => expect(planLabel(workspace.current_plan!)).toBe("Pro · v2"));
  it("derives usage projection from grant and ledger balance", () => expect(creditUsagePercent(workspace)).toBe(25));
  it("keeps entitlements only for active-ish subscription states", () => {
    expect(subscriptionKeepsEntitlements(workspace.subscription)).toBe(true);
    expect(subscriptionKeepsEntitlements({ ...workspace.subscription!, state: "CANCELLED" })).toBe(false);
  });
  it("renders only HTTPS hosted billing links", () => {
    expect(safeHttpsBillingUrl("https://checkout.example.test/session")).toMatch(/^https:/);
    expect(safeHttpsBillingUrl("javascript:alert(1)")).toBeNull();
    expect(safeHttpsBillingUrl("http://billing.example.test")).toBeNull();
  });
});
