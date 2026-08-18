export type PlatformAdminRole =
  | "SUPPORT_READ"
  | "OPS"
  | "BILLING_ADMIN"
  | "AI_CONFIG_ADMIN"
  | "SECURITY_ADMIN"
  | "SUPER_ADMIN";

export type PlatformAdminPrincipal = {
  id: string;
  user_id: string;
  role: PlatformAdminRole;
  permissions: string[];
  active: boolean;
};

export type AdminDashboard = {
  active_runs: number;
  failed_runs: number;
  failed_tasks: number;
  queue_pending: number;
  dlq_open: number;
  degraded_providers: number;
  payment_events_pending: number;
  provider_cost_24h: string;
};

export type SafeRunSummary = {
  id: string;
  organization_id: string;
  project_id: string;
  status: string;
  graph_key: string;
  graph_version: string;
  agent_config_version: string;
  code_git_sha: string;
  budget_amount: string;
  budget_currency: string;
  created_at: string;
  updated_at: string;
};

export type SafeDeadLetter = {
  id: string;
  organization_id: string;
  message_id: string;
  message_kind: string;
  source_queue: string;
  consumer: string;
  error_category: string;
  error_code: string | null;
  error_message: string;
  attempts: number;
  status: string;
  failed_at: string;
  last_failed_at: string;
  replayed_at: string | null;
};

export type ProviderControlSummary = {
  provider: string;
  model: string | null;
  capability: string | null;
  state: string;
  score: number;
  observed_at: string;
  override_action: string | null;
  override_expires_at: string | null;
};

export type FeatureFlag = {
  id: string;
  flag_key: string;
  scope: string;
  target_id: string | null;
  value: Record<string, unknown>;
  owner: string;
  reason: string;
  security_locked: boolean;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
};

const ADMIN_ROLES = new Set<PlatformAdminRole>([
  "SUPPORT_READ",
  "OPS",
  "BILLING_ADMIN",
  "AI_CONFIG_ADMIN",
  "SECURITY_ADMIN",
  "SUPER_ADMIN",
]);

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

function nullableText(value: unknown, label: string): string | null {
  if (value === null) return null;
  return text(value, label);
}

function count(value: unknown, label: string): number {
  if (!Number.isSafeInteger(value) || (value as number) < 0) {
    throw new Error(`${label} must be a non-negative integer`);
  }
  return value as number;
}

function score(value: unknown, label: string): number {
  if (!Number.isSafeInteger(value) || (value as number) < 0 || (value as number) > 100) {
    throw new Error(`${label} must be an integer from 0 to 100`);
  }
  return value as number;
}

function timestamp(value: unknown, label: string): string {
  const raw = text(value, label);
  if (!Number.isFinite(Date.parse(raw))) {
    throw new Error(`${label} must be an ISO timestamp`);
  }
  return raw;
}

function nullableTimestamp(value: unknown, label: string): string | null {
  if (value === null) return null;
  return timestamp(value, label);
}

export function parsePlatformAdminPrincipal(value: unknown): PlatformAdminPrincipal {
  const row = record(value, "platform admin principal");
  const role = text(row.role, "role") as PlatformAdminRole;
  if (!ADMIN_ROLES.has(role)) throw new Error("role is not a platform admin role");
  if (!Array.isArray(row.permissions) || row.permissions.some((item) => typeof item !== "string")) {
    throw new Error("permissions must be a string array");
  }
  if (typeof row.active !== "boolean") throw new Error("active must be boolean");
  return {
    id: text(row.id, "id"),
    user_id: text(row.user_id, "user_id"),
    role,
    permissions: [...row.permissions] as string[],
    active: row.active,
  };
}

export function parseAdminDashboard(value: unknown): AdminDashboard {
  const row = record(value, "admin dashboard");
  return {
    active_runs: count(row.active_runs, "active_runs"),
    failed_runs: count(row.failed_runs, "failed_runs"),
    failed_tasks: count(row.failed_tasks, "failed_tasks"),
    queue_pending: count(row.queue_pending, "queue_pending"),
    dlq_open: count(row.dlq_open, "dlq_open"),
    degraded_providers: count(row.degraded_providers, "degraded_providers"),
    payment_events_pending: count(row.payment_events_pending, "payment_events_pending"),
    provider_cost_24h: text(row.provider_cost_24h, "provider_cost_24h"),
  };
}

export function parseSafeRuns(value: unknown): SafeRunSummary[] {
  if (!Array.isArray(value)) throw new Error("runs must be an array");
  return value.map((item, index) => {
    const row = record(item, `runs[${index}]`);
    return {
      id: text(row.id, "run.id"),
      organization_id: text(row.organization_id, "run.organization_id"),
      project_id: text(row.project_id, "run.project_id"),
      status: text(row.status, "run.status"),
      graph_key: text(row.graph_key, "run.graph_key"),
      graph_version: text(row.graph_version, "run.graph_version"),
      agent_config_version: text(row.agent_config_version, "run.agent_config_version"),
      code_git_sha: text(row.code_git_sha, "run.code_git_sha"),
      budget_amount: text(row.budget_amount, "run.budget_amount"),
      budget_currency: text(row.budget_currency, "run.budget_currency"),
      created_at: timestamp(row.created_at, "run.created_at"),
      updated_at: timestamp(row.updated_at, "run.updated_at"),
    };
  });
}

export function parseDeadLetters(value: unknown): SafeDeadLetter[] {
  if (!Array.isArray(value)) throw new Error("dead letters must be an array");
  return value.map((item, index) => {
    const row = record(item, `dead_letters[${index}]`);
    return {
      id: text(row.id, "dead_letter.id"),
      organization_id: text(row.organization_id, "dead_letter.organization_id"),
      message_id: text(row.message_id, "dead_letter.message_id"),
      message_kind: text(row.message_kind, "dead_letter.message_kind"),
      source_queue: text(row.source_queue, "dead_letter.source_queue"),
      consumer: text(row.consumer, "dead_letter.consumer"),
      error_category: text(row.error_category, "dead_letter.error_category"),
      error_code: nullableText(row.error_code, "dead_letter.error_code"),
      error_message: text(row.error_message, "dead_letter.error_message"),
      attempts: count(row.attempts, "dead_letter.attempts"),
      status: text(row.status, "dead_letter.status"),
      failed_at: timestamp(row.failed_at, "dead_letter.failed_at"),
      last_failed_at: timestamp(row.last_failed_at, "dead_letter.last_failed_at"),
      replayed_at: nullableTimestamp(row.replayed_at, "dead_letter.replayed_at"),
    };
  });
}

export function parseProviders(value: unknown): ProviderControlSummary[] {
  if (!Array.isArray(value)) throw new Error("providers must be an array");
  return value.map((item, index) => {
    const row = record(item, `providers[${index}]`);
    return {
      provider: text(row.provider, "provider.provider"),
      model: nullableText(row.model, "provider.model"),
      capability: nullableText(row.capability, "provider.capability"),
      state: text(row.state, "provider.state"),
      score: score(row.score, "provider.score"),
      observed_at: timestamp(row.observed_at, "provider.observed_at"),
      override_action: nullableText(row.override_action, "provider.override_action"),
      override_expires_at: nullableTimestamp(
        row.override_expires_at,
        "provider.override_expires_at",
      ),
    };
  });
}

export function parseFeatureFlags(value: unknown): FeatureFlag[] {
  if (!Array.isArray(value)) throw new Error("feature flags must be an array");
  return value.map((item, index) => {
    const row = record(item, `feature_flags[${index}]`);
    if (typeof row.security_locked !== "boolean") {
      throw new Error("feature_flag.security_locked must be boolean");
    }
    return {
      id: text(row.id, "feature_flag.id"),
      flag_key: text(row.flag_key, "feature_flag.flag_key"),
      scope: text(row.scope, "feature_flag.scope"),
      target_id: nullableText(row.target_id, "feature_flag.target_id"),
      value: record(row.value, "feature_flag.value"),
      owner: text(row.owner, "feature_flag.owner"),
      reason: text(row.reason, "feature_flag.reason"),
      security_locked: row.security_locked,
      expires_at: nullableTimestamp(row.expires_at, "feature_flag.expires_at"),
      created_at: timestamp(row.created_at, "feature_flag.created_at"),
      updated_at: timestamp(row.updated_at, "feature_flag.updated_at"),
    };
  });
}
