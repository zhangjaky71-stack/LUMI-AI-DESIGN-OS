import { describe, expect, it } from "vitest";
import { assertExactApprovalSubject, historyApprovals, pendingApprovals, policyLabel } from "./contracts";
import type { ApprovalRecord, ApprovalWorkspace } from "./types";

const approval: ApprovalRecord = {
  approval_id: "a1", organization_id: "o", project_id: "p", approval_type: "ARTIFACT_VERSION",
  subject: { subject_type: "ARTIFACT_VERSION", subject_id: "artifact", subject_version: "artifact-v4" },
  status: "PENDING", requested_by: "agent", policy: { mode: "MIN_N", version: 2, required_permission: "artifact.approve", required_roles: [], min_approvals: 2, sequence_roles: [] },
  payload_summary: "Review", agent_run_id: "run", task_id: null, expires_at: null, created_at: "2026-08-15T00:00:00Z",
  resolved_at: null, resolved_by: null, decisions: [], feedback: null, superseded_by: null,
};

it("rejects floating subject versions", () => {
  expect(() => assertExactApprovalSubject({ ...approval, subject: { ...approval.subject, subject_version: "latest" } })).toThrow(/MUST_BE_EXACT/);
  expect(() => assertExactApprovalSubject(approval)).not.toThrow();
});

it("keeps pending and immutable history separate", () => {
  const workspace: ApprovalWorkspace = { project_id: "p", project_name: "P", current_actor_id: "u", can_decide: true, approvals: [approval, { ...approval, approval_id: "a2", status: "SUPERSEDED" }] };
  expect(pendingApprovals(workspace)).toHaveLength(1);
  expect(historyApprovals(workspace)).toHaveLength(1);
  expect(policyLabel(approval)).toContain("2 approvals");
});
