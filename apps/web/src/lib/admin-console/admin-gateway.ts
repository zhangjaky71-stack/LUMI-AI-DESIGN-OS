import { LumiApiClient } from "@/lib/app-shell/api-client";
import type {
  AdminBillingView,
  AdminBootstrap,
  AdminProvider,
  AdminQueueItem,
  AdminRegistryItem,
  AdminRun,
  AdminWorkspace,
  RevealedPii,
  SensitiveActionInput,
  ViewAsSession,
} from "./types";

export interface AdminGateway {
  load(signal?: AbortSignal): Promise<AdminWorkspace>;
  retryRun(runId: string, input: SensitiveActionInput): Promise<AdminRun>;
  cancelRun(runId: string, input: SensitiveActionInput): Promise<AdminRun>;
  disableProvider(providerId: string, expiresAt: string, input: SensitiveActionInput): Promise<AdminProvider>;
  requeue(queueItemId: string, input: SensitiveActionInput): Promise<AdminQueueItem>;
  setRegistryEnabled(item: AdminRegistryItem, enabled: boolean, input: SensitiveActionInput): Promise<AdminRegistryItem>;
  adjustBilling(organizationId: string, deltaCredits: number, input: SensitiveActionInput): Promise<AdminBillingView>;
  revealPii(userId: string, reason: string, ticketRef: string): Promise<RevealedPii>;
  startViewAs(userId: string, organizationId: string, reason: string, ticketRef: string): Promise<ViewAsSession>;
}

function request(signal?: AbortSignal): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

class HttpAdminGateway implements AdminGateway {
  constructor(private readonly api: LumiApiClient) {}

  load(signal?: AbortSignal): Promise<AdminWorkspace> {
    return this.api.get<AdminWorkspace>("/admin/console", request(signal));
  }

  retryRun(runId: string, input: SensitiveActionInput): Promise<AdminRun> {
    return this.api.post<AdminRun, SensitiveActionInput>(
      `/admin/runs/${encodeURIComponent(runId)}:retry`, input,
    );
  }

  cancelRun(runId: string, input: SensitiveActionInput): Promise<AdminRun> {
    return this.api.post<AdminRun, SensitiveActionInput>(
      `/admin/runs/${encodeURIComponent(runId)}:cancel`, input,
    );
  }

  disableProvider(providerId: string, expiresAt: string, input: SensitiveActionInput): Promise<AdminProvider> {
    return this.api.post<AdminProvider, SensitiveActionInput & { expires_at: string }>(
      `/admin/providers/${encodeURIComponent(providerId)}:disable`,
      { ...input, expires_at: expiresAt },
    );
  }

  requeue(queueItemId: string, input: SensitiveActionInput): Promise<AdminQueueItem> {
    return this.api.post<AdminQueueItem, SensitiveActionInput>(
      `/admin/queue/${encodeURIComponent(queueItemId)}:requeue`, input,
    );
  }

  setRegistryEnabled(item: AdminRegistryItem, enabled: boolean, input: SensitiveActionInput): Promise<AdminRegistryItem> {
    return this.api.post<AdminRegistryItem, SensitiveActionInput & { enabled: boolean }>(
      `/admin/registry/${item.kind}/${encodeURIComponent(item.registry_id)}:set-enabled`,
      { ...input, enabled },
    );
  }

  adjustBilling(organizationId: string, deltaCredits: number, input: SensitiveActionInput): Promise<AdminBillingView> {
    return this.api.post<AdminBillingView, SensitiveActionInput & { delta_credits: number }>(
      `/admin/billing/${encodeURIComponent(organizationId)}:adjust`,
      { ...input, delta_credits: deltaCredits },
      { idempotency_key: `admin-adjust-${globalThis.crypto.randomUUID()}` },
    );
  }

  revealPii(userId: string, reason: string, ticketRef: string): Promise<RevealedPii> {
    return this.api.post<RevealedPii, { reason: string; ticket_ref: string }>(
      `/admin/users/${encodeURIComponent(userId)}:reveal-pii`,
      { reason, ticket_ref: ticketRef },
    );
  }

  startViewAs(userId: string, organizationId: string, reason: string, ticketRef: string): Promise<ViewAsSession> {
    return this.api.post<ViewAsSession, { organization_id: string; reason: string; ticket_ref: string; ttl_minutes: number }>(
      `/admin/users/${encodeURIComponent(userId)}:view-as`,
      { organization_id: organizationId, reason, ticket_ref: ticketRef, ttl_minutes: 10 },
    );
  }
}

class DeterministicAdminGateway implements AdminGateway {
  private workspace: AdminWorkspace;

  constructor(workspace: AdminWorkspace) {
    this.workspace = structuredClone(workspace);
  }

  async load(signal?: AbortSignal): Promise<AdminWorkspace> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    return structuredClone(this.workspace);
  }

  async retryRun(runId: string, _input: SensitiveActionInput): Promise<AdminRun> {
    const current = this.workspace.runs.find((item) => item.run_id === runId);
    if (!current) throw new Error("ADMIN_RUN_NOT_FOUND");
    const updated: AdminRun = { ...current, status: "QUEUED", retryable: false };
    this.workspace = { ...this.workspace, runs: this.workspace.runs.map((item) => item.run_id === runId ? updated : item) };
    return updated;
  }

  async cancelRun(runId: string, _input: SensitiveActionInput): Promise<AdminRun> {
    const current = this.workspace.runs.find((item) => item.run_id === runId);
    if (!current) throw new Error("ADMIN_RUN_NOT_FOUND");
    const updated: AdminRun = { ...current, status: "CANCELLED", cancellable: false };
    this.workspace = { ...this.workspace, runs: this.workspace.runs.map((item) => item.run_id === runId ? updated : item) };
    return updated;
  }

  async disableProvider(providerId: string, expiresAt: string, _input: SensitiveActionInput): Promise<AdminProvider> {
    const current = this.workspace.providers.find((item) => item.provider_id === providerId);
    if (!current) throw new Error("ADMIN_PROVIDER_NOT_FOUND");
    const updated: AdminProvider = { ...current, health: "DISABLED", routing_weight_basis_points: 0, disabled_until: expiresAt, disabled_reason: "confirmed admin action" };
    this.workspace = { ...this.workspace, providers: this.workspace.providers.map((item) => item.provider_id === providerId ? updated : item) };
    return updated;
  }

  async requeue(queueItemId: string, _input: SensitiveActionInput): Promise<AdminQueueItem> {
    const current = this.workspace.queue.find((item) => item.queue_item_id === queueItemId);
    if (!current) throw new Error("ADMIN_QUEUE_ITEM_NOT_FOUND");
    const updated: AdminQueueItem = { ...current, state: "READY", attempts: current.attempts + 1 };
    this.workspace = { ...this.workspace, queue: this.workspace.queue.map((item) => item.queue_item_id === queueItemId ? updated : item) };
    return updated;
  }

  async setRegistryEnabled(item: AdminRegistryItem, enabled: boolean, _input: SensitiveActionInput): Promise<AdminRegistryItem> {
    const updated: AdminRegistryItem = { ...item, enabled };
    this.workspace = { ...this.workspace, registry: this.workspace.registry.map((value) => value.registry_id === item.registry_id && value.kind === item.kind ? updated : value) };
    return updated;
  }

  async adjustBilling(organizationId: string, deltaCredits: number, _input: SensitiveActionInput): Promise<AdminBillingView> {
    return { organization_id: organizationId, plan_version_id: "pro-v2", subscription_state: "ACTIVE", credit_balance: 1200 + deltaCredits, invoice_refs: ["inv-6401"] };
  }

  async revealPii(userId: string, _reason: string, _ticketRef: string): Promise<RevealedPii> {
    return { user_id: userId, email: `${userId}@example.test`, phone: "+81 •• •••• 6401" };
  }

  async startViewAs(userId: string, organizationId: string, _reason: string, _ticketRef: string): Promise<ViewAsSession> {
    const started = new Date();
    return { session_id: "view-node64", admin_actor_id: this.workspace.actor.actor_id, target_user_id: userId, target_organization_id: organizationId, readonly: true, started_at: started.toISOString(), expires_at: new Date(started.getTime() + 10 * 60_000).toISOString(), ended_at: null };
  }
}

export function createAdminGateway(bootstrap: AdminBootstrap, api: LumiApiClient): AdminGateway {
  if (bootstrap.deterministic && bootstrap.workspace) return new DeterministicAdminGateway(bootstrap.workspace);
  return new HttpAdminGateway(api);
}
