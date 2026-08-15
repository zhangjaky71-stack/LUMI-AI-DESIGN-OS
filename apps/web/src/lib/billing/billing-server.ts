import type { BillingBootstrap, BillingWorkspace } from "./types";

export function deterministicBillingWorkspace(): BillingWorkspace {
  const currentPlan = {
    plan_id: "pro", plan_version_id: "pro-v2", version: 2, name: "Pro", currency: "USD",
    price_microusd: 49_000_000, billing_interval: "MONTH" as const, monthly_credit_grant: 1000,
    entitlements: { video_enabled: true, max_concurrent_generations: 6, team_seats: 5, brand_kits: 8, priority_routing: true }, status: "ACTIVE" as const,
  };
  return {
    organization_id: "00000000-0000-0000-0000-000000000063",
    current_plan: currentPlan,
    subscription: {
      subscription_id: "sub-e2e-63", organization_id: "00000000-0000-0000-0000-000000000063",
      plan_version_id: "pro-v2", payment_provider: "MOCK", provider_subscription_ref: "mock_sub_63",
      state: "ACTIVE", current_period_start: "2026-08-01T00:00:00Z", current_period_end: "2026-09-01T00:00:00Z", cancel_at_period_end: false,
    },
    plans: [
      currentPlan,
      { ...currentPlan, plan_version_id: "pro-v3", version: 3, price_microusd: 59_000_000, monthly_credit_grant: 1200, entitlements: { ...currentPlan.entitlements, team_seats: 8 } },
    ],
    credit_balance: 870,
    credit_entries: [
      { entry_id: "credit-refund-63", organization_id: "00000000-0000-0000-0000-000000000063", entry_type: "REFUND", delta_credits: 50, source_type: "GENERATION_FAILURE", source_id: "generation-63", pricing_policy_version: 1, idempotency_key: "refund-63", created_at: "2026-08-15T06:00:00Z" },
      { entry_id: "credit-consume-63", organization_id: "00000000-0000-0000-0000-000000000063", entry_type: "CONSUME", delta_credits: -180, source_type: "USAGE", source_id: "usage-63", pricing_policy_version: 1, idempotency_key: "consume-63", created_at: "2026-08-14T05:00:00Z" },
      { entry_id: "credit-grant-63", organization_id: "00000000-0000-0000-0000-000000000063", entry_type: "GRANT", delta_credits: 1000, source_type: "INVOICE", source_id: "invoice-63", pricing_policy_version: null, idempotency_key: "invoice-63-grant", created_at: "2026-08-01T00:00:00Z" },
    ],
    invoices: [{ invoice_id: "invoice-63", organization_id: "00000000-0000-0000-0000-000000000063", provider: "MOCK", provider_invoice_ref: "mock_inv_63", plan_version_id: "pro-v2", status: "PAID", amount_due_microusd: 49_000_000, currency: "USD", hosted_invoice_url: "https://invoice.mock.invalid/mock_inv_63", created_at: "2026-08-01T00:00:00Z" }],
    entitlements: currentPlan.entitlements,
    can_manage: true,
    payment_provider: "MOCK",
    provider_cost_reconciliation_available: false,
  };
}

export function getBillingBootstrap(): BillingBootstrap {
  const deterministic = process.env.NODE_ENV !== "production" && process.env.LUMI_BILLING_E2E === "1";
  return deterministic
    ? { mode: "DETERMINISTIC", workspace: deterministicBillingWorkspace() }
    : { mode: "HTTP", workspace: null };
}
