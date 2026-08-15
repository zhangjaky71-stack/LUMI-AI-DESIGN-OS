import type { PlatformAdminPrincipal } from "@/lib/app-shell/types";
import type { AdminBootstrap, AdminWorkspace } from "./types";

const FIXTURE_MARKER = "node64_admin_fixture_v1";

function fixture(actor: PlatformAdminPrincipal): AdminWorkspace {
  void FIXTURE_MARKER;
  return {
    actor: { actor_id: actor.actor_id, roles: actor.roles, permissions: actor.permissions },
    overview: {
      active_users: 128,
      active_organizations: 24,
      daily_generations: 864,
      failure_rate_basis_points: 275,
      provider_health: "DEGRADED",
      queue_depth: 7,
      cost_today_microusd: 184_250_000,
      critical_alerts: ["PROVIDER_DEGRADED", "QUEUE_DLQ"],
    },
    users: [
      { user_id: "user-support-64", display_name: "Northstar Operator", email_masked: "n•••@example.test", phone_masked: "••••6401", status: "ACTIVE", organization_ids: ["org-lumi"], membership_roles: ["OWNER"], recent_error_codes: ["MODEL_TIMEOUT"] },
      { user_id: "user-viewer-64", display_name: "Studio Reviewer", email_masked: "s•••@example.test", phone_masked: null, status: "ACTIVE", organization_ids: ["org-northstar"], membership_roles: ["VIEWER"], recent_error_codes: [] },
    ],
    runs: [
      { run_id: "run-admin-64", organization_id: "org-lumi", task_id: "task-64", kind: "GENERATION", status: "FAILED", provider: "image-primary", tool: null, error_code: "PROVIDER_TIMEOUT", cost_microusd: 42_000, retryable: true, cancellable: false, created_at: "2026-08-15T07:30:00.000Z" },
      { run_id: "run-admin-65", organization_id: "org-northstar", task_id: "task-65", kind: "AGENT", status: "RUNNING", provider: "reasoning-primary", tool: "design.compose", error_code: null, cost_microusd: 18_000, retryable: false, cancellable: true, created_at: "2026-08-15T07:35:00.000Z" },
    ],
    providers: [
      { provider_id: "image-primary", health: "DEGRADED", circuit: "HALF_OPEN", routing_weight_basis_points: 7000, synthetic_health: "DEGRADED", pricing_snapshot_id: "pricing-image-12", disabled_until: null, disabled_reason: null },
      { provider_id: "reasoning-primary", health: "HEALTHY", circuit: "CLOSED", routing_weight_basis_points: 10000, synthetic_health: "HEALTHY", pricing_snapshot_id: "pricing-reasoning-7", disabled_until: null, disabled_reason: null },
    ],
    queue: [
      { queue_item_id: "queue-64", task_id: "task-64", state: "DLQ", payload_ref: "payload://task-64/v1", payload_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", attempts: 3, last_error_code: "PROVIDER_TIMEOUT" },
      { queue_item_id: "queue-65", task_id: "task-65", state: "RUNNING", payload_ref: "payload://task-65/v1", payload_sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", attempts: 1, last_error_code: null },
    ],
    registry: [
      { registry_id: "designer", kind: "AGENT", name: "Designer Agent", version: "v7", enabled: true, traffic_basis_points: 10000, deploy_diff_summary: "Prompt bundle v7; tool grants unchanged" },
      { registry_id: "brand-compliance", kind: "SKILL", name: "Brand Compliance", version: "v4", enabled: true, traffic_basis_points: 10000, deploy_diff_summary: "Rule evaluator v4" },
    ],
    audit: [
      { event_id: "audit-64", event_type: "ADMIN_QUEUE_REQUEUED", actor_id: actor.actor_id, target_type: "QUEUE_ITEM", target_id: "queue-prior", reason: "resolved provider incident", ticket_ref: "INC-6399", created_at: "2026-08-15T07:10:00.000Z", safe_metadata: [["payload_sha256", "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"]] },
    ],
  };
}

export function getAdminBootstrap(actor: PlatformAdminPrincipal): AdminBootstrap {
  if (process.env.NODE_ENV !== "production" && process.env.LUMI_ADMIN_E2E === "1") {
    return { workspace: fixture(actor), deterministic: true };
  }
  return { workspace: null, deterministic: false };
}
