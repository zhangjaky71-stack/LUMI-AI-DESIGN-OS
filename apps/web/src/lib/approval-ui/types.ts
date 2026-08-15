export type ApprovalType =
  | "CREATIVE_DIRECTION"
  | "ARTIFACT_VERSION"
  | "BRAND_RULE_SET"
  | "BUDGET_INCREASE"
  | "EXTERNAL_PUBLISH"
  | "DESTRUCTIVE_ACTION"
  | "CUSTOM_REVIEW";

export type ApprovalStatus =
  | "PENDING"
  | "APPROVED"
  | "REJECTED"
  | "CHANGES_REQUESTED"
  | "EXPIRED"
  | "CANCELLED"
  | "SUPERSEDED";

export type ApprovalDecision = "APPROVE" | "REJECT" | "REQUEST_CHANGES";
export type ApprovalPolicyMode = "ANY_ONE" | "ALL" | "MIN_N" | "ROLE_BASED_SEQUENCE";

export interface ApprovalSubject {
  readonly subject_type: string;
  readonly subject_id: string;
  readonly subject_version: string;
}

export interface ApprovalPolicy {
  readonly mode: ApprovalPolicyMode;
  readonly version: number;
  readonly required_permission: string;
  readonly required_roles: readonly string[];
  readonly min_approvals: number;
  readonly sequence_roles: readonly string[];
}

export interface ApprovalFeedback {
  readonly comment: string;
  readonly node_refs: readonly string[];
  readonly region_refs: readonly string[];
  readonly requested_changes: readonly string[];
}

export interface ApprovalDecisionRecord {
  readonly decision_id: string;
  readonly approval_id: string;
  readonly actor_id: string;
  readonly actor_roles: readonly string[];
  readonly decision: ApprovalDecision;
  readonly reason: string | null;
  readonly decided_subject_version: string;
  readonly idempotency_key: string;
  readonly created_at: string;
}

export interface ApprovalRecord {
  readonly approval_id: string;
  readonly organization_id: string;
  readonly project_id: string;
  readonly approval_type: ApprovalType;
  readonly subject: ApprovalSubject;
  readonly status: ApprovalStatus;
  readonly requested_by: string;
  readonly policy: ApprovalPolicy;
  readonly payload_summary: string;
  readonly agent_run_id: string | null;
  readonly task_id: string | null;
  readonly expires_at: string | null;
  readonly created_at: string;
  readonly resolved_at: string | null;
  readonly resolved_by: string | null;
  readonly decisions: readonly ApprovalDecisionRecord[];
  readonly feedback: ApprovalFeedback | null;
  readonly superseded_by: string | null;
}

export interface ApprovalWorkspace {
  readonly project_id: string;
  readonly project_name: string;
  readonly current_actor_id: string;
  readonly can_decide: boolean;
  readonly approvals: readonly ApprovalRecord[];
}

export interface ApprovalBootstrap {
  readonly mode: "PRODUCTION" | "DETERMINISTIC";
  readonly workspace: ApprovalWorkspace | null;
}

export interface ApprovalDecisionInput {
  readonly decision: ApprovalDecision;
  readonly reason?: string | null;
  readonly feedback?: ApprovalFeedback | null;
}
