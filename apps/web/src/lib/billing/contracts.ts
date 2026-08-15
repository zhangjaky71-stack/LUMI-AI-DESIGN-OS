import { LumiApiError } from "@/lib/app-shell/api-client";
import type { BillingPlanVersion, BillingSubscription, BillingWorkspace } from "./types";

export function formatMicrousd(value: number, currency = "USD"): string {
  if (!Number.isSafeInteger(value) || value < 0) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(value / 1_000_000);
}

export function planLabel(plan: BillingPlanVersion): string {
  return `${plan.name} · v${plan.version}`;
}

export function subscriptionKeepsEntitlements(subscription: BillingSubscription | null): boolean {
  return subscription !== null && ["TRIALING", "ACTIVE", "CANCEL_AT_PERIOD_END"].includes(subscription.state);
}

export function creditUsagePercent(workspace: BillingWorkspace): number | null {
  const grant = workspace.current_plan?.monthly_credit_grant ?? 0;
  if (grant <= 0) return null;
  const used = Math.max(0, grant - workspace.credit_balance);
  return Math.min(100, Math.round((used / grant) * 100));
}

export function entitlementRows(workspace: BillingWorkspace): readonly [string, string][] {
  return Object.entries(workspace.entitlements).map(([key, value]) => [key, String(value)] as const);
}

export function safeHttpsBillingUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export function safeBillingError(error: unknown): string {
  const code = error instanceof LumiApiError ? error.problem.code : error instanceof Error ? error.message : "BILLING_REQUEST_FAILED";
  switch (code) {
    case "BILLING_FORBIDDEN": return "You do not have permission to manage billing for this organization.";
    case "BILLING_INSUFFICIENT_CREDITS": return "Not enough credits are available for this operation.";
    case "BILLING_WEBHOOK_SIGNATURE_INVALID": return "The payment event could not be verified.";
    case "BILLING_PLAN_VERSION_NOT_AVAILABLE": return "That plan version is no longer available for new checkout sessions.";
    default: return "Billing could not complete the request. Retry or contact an organization owner.";
  }
}
