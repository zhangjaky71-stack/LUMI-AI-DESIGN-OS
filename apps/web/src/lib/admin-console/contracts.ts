import { LumiApiError } from "@/lib/app-shell/api-client";
import type { AdminWorkspace, SensitiveActionInput } from "./types";

export function formatMicrousd(value: number | null): string {
  if (value === null) return "Integration pending";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value / 1_000_000);
}

export function formatBasisPoints(value: number): string {
  return `${(value / 100).toFixed(2)}%`;
}

export function hasAdminPermission(workspace: AdminWorkspace, permission: string): boolean {
  return workspace.actor.permissions.includes(permission);
}

export function sensitiveAction(
  actionSummary: string,
  impactScope: string,
  reason: string,
  ticketRef: string,
  confirmation: string,
): SensitiveActionInput {
  if (!reason.trim() || !ticketRef.trim()) throw new Error("ADMIN_REASON_TICKET_REQUIRED");
  if (confirmation !== "CONFIRM") throw new Error("ADMIN_SECOND_CONFIRMATION_REQUIRED");
  return {
    action_summary: actionSummary,
    impact_scope: impactScope,
    reason: reason.trim(),
    ticket_ref: ticketRef.trim(),
    confirmation: "CONFIRM",
  };
}

export function safeAdminError(value: unknown): string {
  if (value instanceof LumiApiError) {
    const requestId = value.problem.request_id ? ` Request ID: ${value.problem.request_id}` : "";
    const messages: Readonly<Record<string, string>> = {
      ADMIN_FORBIDDEN: "Platform admin permission is required.",
      ADMIN_SECOND_CONFIRMATION_REQUIRED: "Type CONFIRM to authorize this sensitive action.",
      ADMIN_CONFIRMATION_SCOPE_MISMATCH: "The action changed while confirmation was open. Review it again.",
      ADMIN_PROVIDER_DISABLE_EXPIRY_INVALID: "Provider disable window must be in the future and no longer than 24 hours.",
      ADMIN_BILLING_IDEMPOTENCY_KEY_REUSED: "This adjustment key was already used for different content.",
      BILLING_INSUFFICIENT_CREDITS: "This adjustment would make credits negative.",
    };
    return `${messages[value.problem.code] ?? "Admin request failed safely."}${requestId}`;
  }
  return value instanceof Error ? value.message : "Admin request failed safely.";
}
