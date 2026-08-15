export interface AdminActor {
  readonly actor_id: string;
  readonly roles: readonly string[];
  readonly permissions: readonly string[];
}

export interface AdminOverview {
  readonly active_users: number;
  readonly active_organizations: number;
  readonly daily_generations: number;
  readonly failure_rate_basis_points: number;
  readonly provider_health: "HEALTHY" | "DEGRADED" | "UNAVAILABLE" | "DISABLED";
  readonly queue_depth: number;
  readonly cost_today_microusd: number | null;
  readonly critical_alerts: readonly string[];
}

export interface AdminUser {
  readonly user_id: string;
  readonly display_name: string;
  readonly email_masked: string | null;
  readonly phone_masked: string | null;
  readonly status: string;
  readonly organization_ids: readonly string[];
  readonly membership_roles: readonly string[];
  readonly recent_error_codes: readonly string[];
}

export interface RevealedPii {
  readonly user_id: string;
  readonly email: string | null;
  readonly phone: string | null;
}

export interface AdminRun {
  readonly run_id: string;
  readonly organization_id: string;
  readonly task_id: string | null;
  readonly kind: "GENERATION" | "AGENT" | "TOOL";
  readonly status: string;
  readonly provider: string | null;
  readonly tool: string | null;
  readonly error_code: string | null;
  readonly cost_microusd: number | null;
  readonly retryable: boolean;
  readonly cancellable: boolean;
  readonly created_at: string;
}

export interface AdminProvider {
  readonly provider_id: string;
  readonly health: "HEALTHY" | "DEGRADED" | "UNAVAILABLE" | "DISABLED";
  readonly circuit: "CLOSED" | "OPEN" | "HALF_OPEN";
  readonly routing_weight_basis_points: number;
  readonly synthetic_health: "HEALTHY" | "DEGRADED" | "UNAVAILABLE" | "DISABLED";
  readonly pricing_snapshot_id: string | null;
  readonly disabled_until: string | null;
  readonly disabled_reason: string | null;
}

export interface AdminQueueItem {
  readonly queue_item_id: string;
  readonly task_id: string;
  readonly state: "READY" | "RUNNING" | "STUCK" | "DLQ";
  readonly payload_ref: string;
  readonly payload_sha256: string;
  readonly attempts: number;
  readonly last_error_code: string | null;
}

export interface AdminRegistryItem {
  readonly registry_id: string;
  readonly kind: "AGENT" | "SKILL";
  readonly name: string;
  readonly version: string;
  readonly enabled: boolean;
  readonly traffic_basis_points: number;
  readonly deploy_diff_summary: string;
}

export interface AdminAuditEvent {
  readonly event_id: string;
  readonly event_type: string;
  readonly actor_id: string;
  readonly target_type: string;
  readonly target_id: string;
  readonly reason: string;
  readonly ticket_ref: string;
  readonly created_at: string;
  readonly safe_metadata: readonly (readonly [string, string])[];
}

export interface AdminBillingView {
  readonly organization_id: string;
  readonly plan_version_id: string | null;
  readonly subscription_state: string | null;
  readonly credit_balance: number;
  readonly invoice_refs: readonly string[];
}

export interface ViewAsSession {
  readonly session_id: string;
  readonly admin_actor_id: string;
  readonly target_user_id: string;
  readonly target_organization_id: string;
  readonly readonly: true;
  readonly started_at: string;
  readonly expires_at: string;
  readonly ended_at: string | null;
}

export interface AdminWorkspace {
  readonly actor: AdminActor;
  readonly overview: AdminOverview;
  readonly users: readonly AdminUser[];
  readonly runs: readonly AdminRun[];
  readonly providers: readonly AdminProvider[];
  readonly queue: readonly AdminQueueItem[];
  readonly registry: readonly AdminRegistryItem[];
  readonly audit: readonly AdminAuditEvent[];
}

export interface AdminBootstrap {
  readonly workspace: AdminWorkspace | null;
  readonly deterministic: boolean;
}

export interface SensitiveActionInput {
  readonly action_summary: string;
  readonly impact_scope: string;
  readonly reason: string;
  readonly ticket_ref: string;
  readonly confirmation: "CONFIRM";
}
