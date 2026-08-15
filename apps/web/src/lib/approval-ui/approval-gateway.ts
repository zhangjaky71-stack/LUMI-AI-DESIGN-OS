import { LumiApiClient } from "@/lib/app-shell/api-client";
import { assertExactApprovalSubject } from "./contracts";
import type { ApprovalBootstrap, ApprovalDecisionInput, ApprovalRecord, ApprovalWorkspace } from "./types";

interface ApprovalListResponse {
  readonly items: ApprovalRecord[];
  readonly current_actor_id: string;
  readonly can_decide: boolean;
}

export interface ApprovalGateway {
  load(projectId: string, signal?: AbortSignal): Promise<ApprovalWorkspace>;
  decide(projectId: string, approvalId: string, input: ApprovalDecisionInput, signal?: AbortSignal): Promise<ApprovalRecord>;
}

function request(signal?: AbortSignal): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

export class HttpApprovalGateway implements ApprovalGateway {
  readonly #api: LumiApiClient;
  constructor(api = new LumiApiClient()) { this.#api = api; }

  async load(projectId: string, signal?: AbortSignal): Promise<ApprovalWorkspace> {
    const response = await this.#api.get<ApprovalListResponse>(
      `/projects/${encodeURIComponent(projectId)}/approvals`, request(signal),
    );
    response.items.forEach(assertExactApprovalSubject);
    return {
      project_id: projectId,
      project_name: "Approval Center",
      current_actor_id: response.current_actor_id,
      can_decide: response.can_decide,
      approvals: response.items,
    };
  }

  async decide(projectId: string, approvalId: string, input: ApprovalDecisionInput, signal?: AbortSignal): Promise<ApprovalRecord> {
    const result = await this.#api.post<ApprovalRecord, ApprovalDecisionInput>(
      `/projects/${encodeURIComponent(projectId)}/approvals/${encodeURIComponent(approvalId)}:decide`,
      input,
      { idempotency_key: crypto.randomUUID(), ...request(signal) },
    );
    assertExactApprovalSubject(result);
    return result;
  }
}

export class DeterministicApprovalGateway implements ApprovalGateway {
  #workspace: ApprovalWorkspace;
  constructor(workspace: ApprovalWorkspace) { this.#workspace = structuredClone(workspace); }

  async load(projectId: string, signal?: AbortSignal): Promise<ApprovalWorkspace> {
    this.#assert(projectId, signal);
    return structuredClone(this.#workspace);
  }

  async decide(projectId: string, approvalId: string, input: ApprovalDecisionInput, signal?: AbortSignal): Promise<ApprovalRecord> {
    this.#assert(projectId, signal);
    const approval = this.#workspace.approvals.find((item) => item.approval_id === approvalId);
    if (!approval || approval.status !== "PENDING") throw new Error("APPROVAL_STALE");
    if (!this.#workspace.can_decide) throw new Error("APPROVAL_FORBIDDEN");
    if (input.decision === "REQUEST_CHANGES" && !input.feedback?.comment.trim() && !input.feedback?.requested_changes.length) {
      throw new Error("APPROVAL_CHANGES_FEEDBACK_REQUIRED");
    }
    const status = input.decision === "APPROVE" ? "APPROVED" : input.decision === "REJECT" ? "REJECTED" : "CHANGES_REQUESTED";
    const updated: ApprovalRecord = {
      ...approval,
      status,
      resolved_at: "2026-08-15T07:00:00.000Z",
      resolved_by: this.#workspace.current_actor_id,
      feedback: input.feedback ?? null,
      decisions: [...approval.decisions, {
        decision_id: `decision-${approvalId}`,
        approval_id: approvalId,
        actor_id: this.#workspace.current_actor_id,
        actor_roles: ["OWNER"],
        decision: input.decision,
        reason: input.reason ?? null,
        decided_subject_version: approval.subject.subject_version,
        idempotency_key: `e2e-${approvalId}`,
        created_at: "2026-08-15T07:00:00.000Z",
      }],
    };
    this.#workspace = { ...this.#workspace, approvals: this.#workspace.approvals.map((item) => item.approval_id === approvalId ? updated : item) };
    return structuredClone(updated);
  }

  #assert(projectId: string, signal?: AbortSignal): void {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (projectId !== this.#workspace.project_id) throw new Error("APPROVAL_PROJECT_NOT_FOUND");
  }
}

export function createApprovalGateway(bootstrap: ApprovalBootstrap): ApprovalGateway {
  return bootstrap.mode === "DETERMINISTIC" && bootstrap.workspace
    ? new DeterministicApprovalGateway(bootstrap.workspace)
    : new HttpApprovalGateway();
}
