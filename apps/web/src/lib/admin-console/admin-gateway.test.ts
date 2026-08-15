import { describe, expect, it } from "vitest";
import { LumiApiClient } from "@/lib/app-shell/api-client";
import { createAdminGateway } from "./admin-gateway";
import type { AdminBootstrap, SensitiveActionInput } from "./types";

const confirm: SensitiveActionInput = {
  action_summary: "Requeue item queue-1",
  impact_scope: "queue-item:queue-1",
  reason: "incident",
  ticket_ref: "INC-64",
  confirmation: "CONFIRM",
};

const bootstrap: AdminBootstrap = {
  deterministic: true,
  workspace: {
    actor: { actor_id: "admin-1", roles: ["OPS"], permissions: ["admin.queue.requeue"] },
    overview: { active_users: 1, active_organizations: 1, daily_generations: 1, failure_rate_basis_points: 0, provider_health: "HEALTHY", queue_depth: 1, cost_today_microusd: null, critical_alerts: [] },
    users: [], runs: [], providers: [], registry: [], audit: [],
    queue: [{ queue_item_id: "queue-1", task_id: "task-1", state: "DLQ", payload_ref: "payload://immutable/1", payload_sha256: "a".repeat(64), attempts: 2, last_error_code: "FAIL" }],
  },
};


describe("NODE-64 deterministic admin gateway", () => {
  it("requeues without changing immutable payload identity", async () => {
    const gateway = createAdminGateway(bootstrap, new LumiApiClient());
    const before = (await gateway.load()).queue[0];
    const after = await gateway.requeue("queue-1", confirm);
    expect(after.state).toBe("READY");
    expect(after.payload_ref).toBe(before?.payload_ref);
    expect(after.payload_sha256).toBe(before?.payload_sha256);
  });

  it("view-as is always readonly", async () => {
    const gateway = createAdminGateway(bootstrap, new LumiApiClient());
    const session = await gateway.startViewAs("user-1", "org-1", "support", "SUP-1");
    expect(session.readonly).toBe(true);
    expect(session.ended_at).toBeNull();
  });
});
