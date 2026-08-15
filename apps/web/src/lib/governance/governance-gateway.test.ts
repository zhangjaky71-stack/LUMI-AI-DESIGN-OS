import { describe, expect, it } from "vitest";
import { createGovernanceGateway } from "./governance-gateway";
import type { GovernanceBootstrap, GovernanceWorkspace } from "./types";

function workspace(): GovernanceWorkspace {
  return {
    organization_id: "org-a",
    capabilities: { can_read_audit: true, can_export_audit: true, can_manage_retention: true, can_manage_holds: true, can_manage_deletion: true },
    audit: {
      items: Array.from({ length: 5 }, (_, index) => ({
        event_id: `audit-${index}`, organization_id: "org-a", actor_type: "USER" as const, actor_id: "u", actor_version: null,
        action: index % 2 ? "PROJECT_ARCHIVED" : "ARTIFACT_APPROVED", resource_type: "PROJECT", resource_id: `r-${index}`,
        resource_version: null, result: index === 3 ? "DENIED" as const : "SUCCESS" as const, reason_code: "TEST", request_id: null,
        trace_id: null, retention_class: "SECURITY_AUDIT" as const, retention_policy_version: 1, correction_of_event_id: null,
        occurred_at: `2026-08-15T00:00:0${index}Z`, event_hash: "a".repeat(64),
      })),
      next_cursor: null,
    },
    retention_policies: [], retention_candidates: [], legal_holds: [], deletions: [], exports: [],
  };
}

function gateway() {
  const bootstrap: GovernanceBootstrap = { mode: "DETERMINISTIC", workspace: workspace() };
  return createGovernanceGateway(bootstrap, {} as never, "org-a");
}

describe("deterministic governance gateway", () => {
  it("filters and cursor-pages audit events without inventing offsets in production contract", async () => {
    const result = await gateway().searchAudit({ action: "ARTIFACT" });
    expect(result.items).toHaveLength(2);
    expect(result.next_cursor).toBe("cursor-2");
  });

  it("legal hold blocks a subject deletion until released", async () => {
    const value = gateway();
    const hold = await value.createHold("USER", "subject-1", "LEGAL_CASE", "LEGAL-65");
    const request = await value.requestDeletion("subject-1");
    expect(request.status).toBe("BLOCKED_HOLD");
    await value.releaseHold(hold.hold_id, "CLOSED", "LEGAL-65");
    const completed = await value.executeDeletion(request.request_id);
    expect(completed.status).toBe("COMPLETED");
    expect(completed.retained_count).toBe(1);
  });

  it("refreshes signed leases without rerendering the export job", async () => {
    const value = gateway();
    const job = await value.createExport("JSON", {});
    const first = await value.getDownload(job.job_id);
    const second = await value.getDownload(job.job_id);
    expect(first.signed_url).not.toBe(second.signed_url);
    expect((await value.load()).exports).toHaveLength(1);
  });
});
