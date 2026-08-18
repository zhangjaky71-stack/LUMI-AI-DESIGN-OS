export const APPROVAL_STATUSES = [
  "PENDING",
  "APPROVED",
  "REJECTED",
  "CHANGES_REQUESTED",
  "EXPIRED",
  "CANCELLED",
  "SUPERSEDED",
] as const;
export type ApprovalStatus = (typeof APPROVAL_STATUSES)[number];

export const APPROVAL_DECISIONS = ["APPROVED", "REJECTED", "CHANGES_REQUESTED"] as const;
export type ApprovalDecision = (typeof APPROVAL_DECISIONS)[number];

export type ApprovalResource = {
  id: string;
  projectId: string;
  agentRunId?: string | null;
  taskId?: string | null;
  approvalType: string;
  subjectType: string;
  subjectId: string;
  subjectVersionRef: string;
  artifactVersionId?: string | null;
  status: ApprovalStatus;
  requestedBy: string;
  requiredPermission: string;
  policyMode: string;
  policyVersion: number;
  minApprovals: number;
  title: string;
  summary: string;
  expiresAt?: string | null;
  resolvedAt?: string | null;
  createdAt: string;
  updatedAt: string;
  version: number;
};

export type ApprovalEffectResource = {
  id: string;
  effectType: "ARTIFACT_VERSION_APPROVE" | "AGENT_RUN_RESUME";
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  attemptCount: number;
  hasError: boolean;
  completedAt?: string | null;
};

export type ApprovalDecisionResult = {
  approval: ApprovalResource;
  decisionId: string;
  effects: readonly ApprovalEffectResource[];
};

const STATUS = new Set<string>(APPROVAL_STATUSES);
const EFFECT_TYPE = new Set(["ARTIFACT_VERSION_APPROVE", "AGENT_RUN_RESUME"]);
const EFFECT_STATUS = new Set(["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]);
const FORBIDDEN_KEYS = new Set([
  "interrupt_id",
  "resume_version",
  "payload",
  "payload_json",
  "last_error",
  "prompt",
  "reasoning",
  "provider_request_id",
  "storage_key",
]);

export function parseApprovalResource(value: unknown): ApprovalResource {
  const record = objectValue(value, "APPROVAL_INVALID");
  rejectForbiddenKeys(record);
  const status = stringValue(record.status, "APPROVAL_STATUS_REQUIRED");
  if (!STATUS.has(status)) throw new Error("APPROVAL_STATUS_INVALID");
  return {
    id: stringValue(record.id, "APPROVAL_ID_REQUIRED"),
    projectId: stringValue(record.project_id ?? record.projectId, "APPROVAL_PROJECT_REQUIRED"),
    agentRunId: optionalString(record.agent_run_id ?? record.agentRunId),
    taskId: optionalString(record.task_id ?? record.taskId),
    approvalType: stringValue(record.approval_type ?? record.approvalType, "APPROVAL_TYPE_REQUIRED"),
    subjectType: stringValue(record.subject_type ?? record.subjectType, "APPROVAL_SUBJECT_TYPE_REQUIRED"),
    subjectId: stringValue(record.subject_id ?? record.subjectId, "APPROVAL_SUBJECT_REQUIRED"),
    subjectVersionRef: stringValue(record.subject_version_ref ?? record.subjectVersionRef, "APPROVAL_SUBJECT_VERSION_REQUIRED"),
    artifactVersionId: optionalString(record.artifact_version_id ?? record.artifactVersionId),
    status: status as ApprovalStatus,
    requestedBy: stringValue(record.requested_by ?? record.requestedBy, "APPROVAL_REQUESTER_REQUIRED"),
    requiredPermission: stringValue(record.required_permission ?? record.requiredPermission, "APPROVAL_PERMISSION_REQUIRED"),
    policyMode: stringValue(record.policy_mode ?? record.policyMode, "APPROVAL_POLICY_MODE_REQUIRED"),
    policyVersion: integerValue(record.policy_version ?? record.policyVersion, 1, "APPROVAL_POLICY_VERSION_INVALID"),
    minApprovals: integerValue(record.min_approvals ?? record.minApprovals, 1, "APPROVAL_MIN_APPROVALS_INVALID"),
    title: stringValue(record.title, "APPROVAL_TITLE_REQUIRED"),
    summary: stringValue(record.summary, "APPROVAL_SUMMARY_REQUIRED"),
    expiresAt: optionalString(record.expires_at ?? record.expiresAt),
    resolvedAt: optionalString(record.resolved_at ?? record.resolvedAt),
    createdAt: stringValue(record.created_at ?? record.createdAt, "APPROVAL_CREATED_AT_REQUIRED"),
    updatedAt: stringValue(record.updated_at ?? record.updatedAt, "APPROVAL_UPDATED_AT_REQUIRED"),
    version: integerValue(record.version, 1, "APPROVAL_VERSION_INVALID"),
  };
}

export function parseApprovalList(value: unknown): ApprovalResource[] {
  if (!Array.isArray(value)) throw new Error("APPROVAL_LIST_INVALID");
  return value.map(parseApprovalResource);
}

export function parseApprovalEffect(value: unknown): ApprovalEffectResource {
  const record = objectValue(value, "APPROVAL_EFFECT_INVALID");
  rejectForbiddenKeys(record);
  const effectType = stringValue(record.effect_type ?? record.effectType, "APPROVAL_EFFECT_TYPE_REQUIRED");
  const status = stringValue(record.status, "APPROVAL_EFFECT_STATUS_REQUIRED");
  if (!EFFECT_TYPE.has(effectType)) throw new Error("APPROVAL_EFFECT_TYPE_INVALID");
  if (!EFFECT_STATUS.has(status)) throw new Error("APPROVAL_EFFECT_STATUS_INVALID");
  return {
    id: stringValue(record.id, "APPROVAL_EFFECT_ID_REQUIRED"),
    effectType: effectType as ApprovalEffectResource["effectType"],
    status: status as ApprovalEffectResource["status"],
    attemptCount: integerValue(record.attempt_count ?? record.attemptCount, 0, "APPROVAL_EFFECT_ATTEMPTS_INVALID"),
    hasError: booleanValue(record.has_error ?? record.hasError, "APPROVAL_EFFECT_ERROR_FLAG_INVALID"),
    completedAt: optionalString(record.completed_at ?? record.completedAt),
  };
}

export function parseApprovalDecisionResult(value: unknown): ApprovalDecisionResult {
  const record = objectValue(value, "APPROVAL_DECISION_RESULT_INVALID");
  const effects = record.effects ?? [];
  if (!Array.isArray(effects)) throw new Error("APPROVAL_EFFECT_LIST_INVALID");
  return {
    approval: parseApprovalResource(record.approval),
    decisionId: stringValue(record.decision_id ?? record.decisionId, "APPROVAL_DECISION_ID_REQUIRED"),
    effects: effects.map(parseApprovalEffect),
  };
}

function rejectForbiddenKeys(record: Record<string, unknown>): void {
  for (const key of Object.keys(record)) {
    if (FORBIDDEN_KEYS.has(key.toLowerCase())) throw new Error("APPROVAL_PRIVATE_FIELD_FORBIDDEN");
  }
}
function objectValue(value: unknown, code: string): Record<string, unknown> { if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(code); return value as Record<string, unknown>; }
function stringValue(value: unknown, code: string): string { if (typeof value !== "string" || !value.trim()) throw new Error(code); return value; }
function optionalString(value: unknown): string | null | undefined { if (value === undefined || value === null) return value; if (typeof value !== "string") throw new Error("APPROVAL_OPTIONAL_STRING_INVALID"); return value; }
function integerValue(value: unknown, min: number, code: string): number { if (!Number.isInteger(value) || (value as number) < min) throw new Error(code); return value as number; }
function booleanValue(value: unknown, code: string): boolean { if (typeof value !== "boolean") throw new Error(code); return value; }
