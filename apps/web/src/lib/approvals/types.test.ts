import { describe, expect, it } from "vitest";

import {
  parseApprovalDecisionResult,
  parseApprovalEffect,
  parseApprovalResource,
} from "./types";

const approval = {
  id: "01911111-1111-7111-8111-111111111111",
  project_id: "01922222-2222-7222-8222-222222222222",
  agent_run_id: null,
  task_id: null,
  approval_type: "ARTIFACT_VERSION",
  subject_type: "ARTIFACT_VERSION",
  subject_id: "01933333-3333-7333-8333-333333333333",
  subject_version_ref: "artifact:v3",
  artifact_version_id: "01933333-3333-7333-8333-333333333333",
  status: "PENDING",
  requested_by: "01944444-4444-7444-8444-444444444444",
  required_permission: "artifact.approve",
  policy_mode: "ANY_ONE",
  policy_version: 1,
  min_approvals: 1,
  title: "Approve hero v3",
  summary: "Review this exact artifact version.",
  expires_at: null,
  resolved_at: null,
  created_at: "2026-08-18T05:00:00Z",
  updated_at: "2026-08-18T05:00:00Z",
  version: 1,
};

describe("approval public contracts", () => {
  it("parses an exact ArtifactVersion approval", () => {
    const parsed = parseApprovalResource(approval);
    expect(parsed.artifactVersionId).toBe(approval.subject_id);
    expect(parsed.subjectVersionRef).toBe("artifact:v3");
    expect(parsed.requiredPermission).toBe("artifact.approve");
  });

  it.each([
    ["interrupt_id", "interrupt-1"],
    ["resume_version", 7],
    ["payload", { secret: "x" }],
    ["payload_json", { secret: "x" }],
    ["last_error", "provider trace"],
    ["provider_request_id", "provider-123"],
    ["storage_key", "private/key"],
  ])("rejects private field %s", (key, value) => {
    expect(() => parseApprovalResource({ ...approval, [key]: value })).toThrow(
      "APPROVAL_PRIVATE_FIELD_FORBIDDEN",
    );
  });

  it("parses safe effect state without raw payload or error", () => {
    const parsed = parseApprovalEffect({
      id: "01955555-5555-7555-8555-555555555555",
      effect_type: "ARTIFACT_VERSION_APPROVE",
      status: "FAILED",
      attempt_count: 2,
      has_error: true,
      completed_at: null,
    });
    expect(parsed.hasError).toBe(true);
    expect(parsed.attemptCount).toBe(2);
  });

  it("rejects raw effect internals", () => {
    expect(() =>
      parseApprovalEffect({
        id: "01955555-5555-7555-8555-555555555555",
        effect_type: "AGENT_RUN_RESUME",
        status: "FAILED",
        attempt_count: 1,
        has_error: true,
        payload: { interrupt_id: "secret-control-id" },
      }),
    ).toThrow("APPROVAL_PRIVATE_FIELD_FORBIDDEN");
  });

  it("parses a safe decision result", () => {
    const result = parseApprovalDecisionResult({
      approval: { ...approval, status: "APPROVED", version: 2 },
      decision_id: "01966666-6666-7666-8666-666666666666",
      effects: [
        {
          id: "01955555-5555-7555-8555-555555555555",
          effect_type: "ARTIFACT_VERSION_APPROVE",
          status: "PENDING",
          attempt_count: 0,
          has_error: false,
          completed_at: null,
        },
      ],
    });
    expect(result.approval.status).toBe("APPROVED");
    expect(result.effects).toHaveLength(1);
  });
});
