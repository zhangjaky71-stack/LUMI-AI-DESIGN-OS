import { LumiApiClient } from "@/lib/app-shell/api-client";
import type { BillingBootstrap, BillingSubscription, BillingWorkspace, HostedBillingSession } from "./types";

export interface BillingGateway {
  load(signal?: AbortSignal): Promise<BillingWorkspace>;
  createCheckout(planVersionId: string, signal?: AbortSignal): Promise<HostedBillingSession>;
  createPortal(signal?: AbortSignal): Promise<HostedBillingSession>;
  cancelSubscription(signal?: AbortSignal): Promise<BillingSubscription>;
}

function request(signal?: AbortSignal): { signal?: AbortSignal } { return signal ? { signal } : {}; }

export class HttpBillingGateway implements BillingGateway {
  readonly #api: LumiApiClient;
  constructor(api = new LumiApiClient()) { this.#api = api; }
  load(signal?: AbortSignal): Promise<BillingWorkspace> {
    return this.#api.get<BillingWorkspace>("/billing", request(signal));
  }
  createCheckout(planVersionId: string, signal?: AbortSignal): Promise<HostedBillingSession> {
    return this.#api.post<HostedBillingSession, { plan_version_id: string }>(
      "/billing/checkout", { plan_version_id: planVersionId }, request(signal),
    );
  }
  createPortal(signal?: AbortSignal): Promise<HostedBillingSession> {
    return this.#api.post<HostedBillingSession, Record<string, never>>(
      "/billing/portal", {}, request(signal),
    );
  }
  cancelSubscription(signal?: AbortSignal): Promise<BillingSubscription> {
    return this.#api.post<BillingSubscription, Record<string, never>>(
      "/billing/subscription:cancel", {}, request(signal),
    );
  }
}

export class DeterministicBillingGateway implements BillingGateway {
  #workspace: BillingWorkspace;
  constructor(workspace: BillingWorkspace) { this.#workspace = structuredClone(workspace); }
  async load(signal?: AbortSignal): Promise<BillingWorkspace> {
    this.#abort(signal);
    return structuredClone(this.#workspace);
  }
  async createCheckout(planVersionId: string, signal?: AbortSignal): Promise<HostedBillingSession> {
    this.#abort(signal);
    if (!this.#workspace.can_manage) throw new Error("BILLING_FORBIDDEN");
    if (!this.#workspace.plans.some((item) => item.plan_version_id === planVersionId)) {
      throw new Error("BILLING_PLAN_VERSION_NOT_AVAILABLE");
    }
    return {
      provider: "MOCK",
      session_ref: `checkout-${planVersionId}`,
      url: `https://checkout.mock.invalid/session/${planVersionId}`,
    };
  }
  async createPortal(signal?: AbortSignal): Promise<HostedBillingSession> {
    this.#abort(signal);
    if (!this.#workspace.can_manage) throw new Error("BILLING_FORBIDDEN");
    return {
      provider: "MOCK",
      session_ref: "portal-org-1",
      url: "https://portal.mock.invalid/session/org-1",
    };
  }
  async cancelSubscription(signal?: AbortSignal): Promise<BillingSubscription> {
    this.#abort(signal);
    if (!this.#workspace.can_manage || !this.#workspace.subscription) {
      throw new Error("BILLING_FORBIDDEN");
    }
    const subscription: BillingSubscription = {
      ...this.#workspace.subscription,
      state: "CANCEL_AT_PERIOD_END",
      cancel_at_period_end: true,
    };
    this.#workspace = { ...this.#workspace, subscription };
    return structuredClone(subscription);
  }
  #abort(signal?: AbortSignal): void {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  }
}

export function createBillingGateway(bootstrap: BillingBootstrap): BillingGateway {
  return bootstrap.mode === "DETERMINISTIC" && bootstrap.workspace
    ? new DeterministicBillingGateway(bootstrap.workspace)
    : new HttpBillingGateway();
}
