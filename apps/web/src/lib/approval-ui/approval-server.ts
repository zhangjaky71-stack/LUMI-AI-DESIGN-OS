import type { ApprovalBootstrap, ApprovalRecord, ApprovalWorkspace } from "./types";

function fixture(projectId: string): ApprovalWorkspace {
  const pending: ApprovalRecord = {
    approval_id: "approval-node62-pending",
    organization_id: "org-lumi-design",
    project_id: projectId,
    approval_type: "ARTIFACT_VERSION",
    subject: { subject_type: "ARTIFACT_VERSION", subject_id: "artifact-summer-launch", subject_version: "artifact-v4" },
    status: "PENDING",
    requested_by: "agent-lumi",
    policy: { mode: "ANY_ONE", version: 1, required_permission: "artifact.approve", required_roles: ["OWNER", "ADMIN"], min_approvals: 1, sequence_roles: [] },
    payload_summary: "Approve the exact campaign master before export and publish.",
    agent_run_id: "approval-e2e-run-62",
    task_id: "task-review-master",
    expires_at: "2026-08-16T07:00:00.000Z",
    created_at: "2026-08-15T06:58:00.000Z",
    resolved_at: null,
    resolved_by: null,
    decisions: [],
    feedback: null,
    superseded_by: null,
  };
  const superseded: ApprovalRecord = {
    ...pending,
    approval_id: "approval-node62-v3",
    subject: { ...pending.subject, subject_version: "artifact-v3" },
    status: "SUPERSEDED",
    created_at: "2026-08-15T06:40:00.000Z",
    resolved_at: "2026-08-15T06:58:00.000Z",
    superseded_by: pending.approval_id,
  };
  const changes: ApprovalRecord = {
    ...pending,
    approval_id: "approval-node62-changes",
    approval_type: "CREATIVE_DIRECTION",
    subject: { subject_type: "CREATIVE_DIRECTION", subject_id: "direction-editorial-a", subject_version: "direction-v2" },
    status: "CHANGES_REQUESTED",
    payload_summary: "Review editorial direction before generating the final family.",
    agent_run_id: "approval-e2e-run-61",
    task_id: "task-direction",
    expires_at: null,
    resolved_at: "2026-08-15T06:48:00.000Z",
    resolved_by: "user-owner",
    feedback: { comment: "Reduce visual density and preserve the approved logo safe zone.", node_refs: ["hero-title"], region_refs: ["frame-instagram:hero"], requested_changes: ["Reduce decorative elements", "Keep logo safe zone"] },
    decisions: [{ decision_id: "decision-changes", approval_id: "approval-node62-changes", actor_id: "user-owner", actor_roles: ["OWNER"], decision: "REQUEST_CHANGES", reason: null, decided_subject_version: "direction-v2", idempotency_key: "fixture-changes", created_at: "2026-08-15T06:48:00.000Z" }],
  };
  return {
    project_id: projectId,
    project_name: "Summer Launch",
    current_actor_id: "user-owner",
    can_decide: true,
    approvals: [pending, superseded, changes],
  };
}

export function getApprovalBootstrap(projectId: string): ApprovalBootstrap {
  const deterministic = process.env.NODE_ENV !== "production" && process.env.LUMI_APPROVAL_E2E === "1";
  return deterministic
    ? { mode: "DETERMINISTIC", workspace: fixture(projectId) }
    : { mode: "PRODUCTION", workspace: null };
}
