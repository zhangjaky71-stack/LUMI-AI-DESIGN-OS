import { describe, expect, it } from "vitest";
import { DeterministicApprovalGateway } from "./approval-gateway";
import type { ApprovalWorkspace } from "./types";

const workspace: ApprovalWorkspace = {
  project_id: "p", project_name: "P", current_actor_id: "owner", can_decide: true,
  approvals: [{
    approval_id: "a1", organization_id: "o", project_id: "p", approval_type: "ARTIFACT_VERSION",
    subject: { subject_type: "ARTIFACT_VERSION", subject_id: "artifact", subject_version: "artifact-v4" },
    status: "PENDING", requested_by: "agent", policy: { mode: "ANY_ONE", version: 1, required_permission: "artifact.approve", required_roles: ["OWNER"], min_approvals: 1, sequence_roles: [] },
    payload_summary: "Review", agent_run_id: "run", task_id: null, expires_at: null, created_at: "2026-08-15T00:00:00Z",
    resolved_at: null, resolved_by: null, decisions: [], feedback: null, superseded_by: null,
  }],
};

describe("deterministic approval gateway", () => {
  it("approves the exact immutable subject", async () => {
    const gateway = new DeterministicApprovalGateway(workspace);
    const result = await gateway.decide("p", "a1", { decision: "APPROVE" });
    expect(result.status).toBe("APPROVED");
    expect(result.subject.subject_version).toBe("artifact-v4");
    expect(result.decisions[0].decided_subject_version).toBe("artifact-v4");
  });

  it("requires feedback for request changes", async () => {
    const gateway = new DeterministicApprovalGateway(workspace);
    await expect(gateway.decide("p", "a1", { decision: "REQUEST_CHANGES", feedback: { comment: "", node_refs: [], region_refs: [], requested_changes: [] } })).rejects.toThrow(/FEEDBACK_REQUIRED/);
  });
});
