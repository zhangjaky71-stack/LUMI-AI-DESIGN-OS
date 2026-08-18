export const SAFE_AGENT_EVENT_TYPES = [
  "run.started",
  "node.started",
  "agent.status",
  "agent.delta",
  "tool.call",
  "task.progress",
  "approval.required",
  "artifact.created",
  "run.completed",
  "run.cancelled",
  "run.waiting_external",
] as const;

export type SafeAgentEventType = (typeof SAFE_AGENT_EVENT_TYPES)[number];

export type AgentRunResource = {
  id: string;
  projectId: string;
  threadId: string;
  graphVersion: string;
  agentConfigVersion: string;
  status: string;
  version: number;
};

export type RunInterrupt = {
  id: string;
  kind: string;
  node?: string | null;
  resumable: boolean;
};

export type RunControlSnapshot = {
  agentRunId: string;
  projectId: string;
  taskId?: string | null;
  threadId: string;
  graphKey: string;
  graphVersion: string;
  codeGitSha: string;
  status: string;
  checkpointId?: string | null;
  resumeVersion: number;
  nextNodes: readonly string[];
  interrupts: readonly RunInterrupt[];
  contextRefs: readonly string[];
  artifactRefs: readonly string[];
  budgetRemaining?: string | null;
  route?: string | null;
  repairIteration: number;
  maxRepairIterations: number;
  errorCode?: string | null;
  updatedAt: string;
};

export type SafeRunEvent = {
  eventId: string;
  eventType: SafeAgentEventType;
  agentRunId: string;
  projectId: string;
  occurredAt: string;
  payload: Readonly<Record<string, unknown>>;
};

export type CanvasSelectionContext = {
  documentVersion: number;
  nodeIds: readonly string[];
};

export type ExactArtifactRef = {
  artifactId: string;
  artifactVersionId: string;
  versionNumber?: number;
  label?: string;
  previewRef?: string;
};

const FORBIDDEN_PUBLIC_KEYS = new Set([
  "prompt",
  "messages",
  "reasoning",
  "chain_of_thought",
  "scratchpad",
  "raw_response",
  "tool_output",
]);
const EVENT_TYPES = new Set<string>(SAFE_AGENT_EVENT_TYPES);

export function parseAgentRunResource(value: unknown): AgentRunResource {
  const record = asRecord(value, "AGENT_RUN_INVALID");
  return {
    id: requiredString(record.id, "AGENT_RUN_ID_REQUIRED"),
    projectId: requiredString(record.project_id ?? record.projectId, "AGENT_RUN_PROJECT_REQUIRED"),
    threadId: requiredString(record.thread_id ?? record.threadId, "AGENT_RUN_THREAD_REQUIRED"),
    graphVersion: requiredString(record.graph_version ?? record.graphVersion, "AGENT_RUN_GRAPH_VERSION_REQUIRED"),
    agentConfigVersion: requiredString(record.agent_config_version ?? record.agentConfigVersion, "AGENT_RUN_CONFIG_VERSION_REQUIRED"),
    status: requiredString(record.status, "AGENT_RUN_STATUS_REQUIRED"),
    version: requiredInteger(record.version, "AGENT_RUN_VERSION_REQUIRED", 1),
  };
}

export function parseRunControlSnapshot(value: unknown): RunControlSnapshot {
  const record = asRecord(value, "RUN_CONTROL_INVALID");
  const interruptsRaw = arrayValue(record.interrupts, "RUN_INTERRUPTS_INVALID");
  return {
    agentRunId: requiredString(record.agent_run_id ?? record.agentRunId, "RUN_ID_REQUIRED"),
    projectId: requiredString(record.project_id ?? record.projectId, "RUN_PROJECT_REQUIRED"),
    taskId: optionalString(record.task_id ?? record.taskId),
    threadId: requiredString(record.thread_id ?? record.threadId, "RUN_THREAD_REQUIRED"),
    graphKey: requiredString(record.graph_key ?? record.graphKey, "RUN_GRAPH_KEY_REQUIRED"),
    graphVersion: requiredString(record.graph_version ?? record.graphVersion, "RUN_GRAPH_VERSION_REQUIRED"),
    codeGitSha: requiredString(record.code_git_sha ?? record.codeGitSha, "RUN_CODE_SHA_REQUIRED"),
    status: requiredString(record.status, "RUN_STATUS_REQUIRED"),
    checkpointId: optionalString(record.checkpoint_id ?? record.checkpointId),
    resumeVersion: requiredInteger(record.resume_version ?? record.resumeVersion, "RUN_RESUME_VERSION_REQUIRED", 1),
    nextNodes: stringArray(record.next_nodes ?? record.nextNodes, "RUN_NEXT_NODES_INVALID"),
    interrupts: interruptsRaw.map(parseInterrupt),
    contextRefs: stringArray(record.context_refs ?? record.contextRefs ?? [], "RUN_CONTEXT_REFS_INVALID"),
    artifactRefs: stringArray(record.artifact_refs ?? record.artifactRefs ?? [], "RUN_ARTIFACT_REFS_INVALID"),
    budgetRemaining: optionalString(record.budget_remaining ?? record.budgetRemaining),
    route: optionalString(record.route),
    repairIteration: optionalInteger(record.repair_iteration ?? record.repairIteration, 0),
    maxRepairIterations: optionalInteger(record.max_repair_iterations ?? record.maxRepairIterations, 0),
    errorCode: optionalString(record.error_code ?? record.errorCode),
    updatedAt: requiredString(record.updated_at ?? record.updatedAt, "RUN_UPDATED_AT_REQUIRED"),
  };
}

export function parseSafeRunEvent(value: unknown): SafeRunEvent {
  const record = asRecord(value, "RUN_EVENT_INVALID");
  const eventType = requiredString(record.event_type ?? record.eventType, "RUN_EVENT_TYPE_REQUIRED");
  if (!EVENT_TYPES.has(eventType)) throw new Error("RUN_EVENT_TYPE_UNSAFE");
  const payload = asRecord(record.payload ?? {}, "RUN_EVENT_PAYLOAD_INVALID");
  assertPublicPayload(payload);
  return {
    eventId: requiredString(record.event_id ?? record.eventId, "RUN_EVENT_ID_REQUIRED"),
    eventType: eventType as SafeAgentEventType,
    agentRunId: requiredString(record.agent_run_id ?? record.agentRunId, "RUN_EVENT_RUN_REQUIRED"),
    projectId: requiredString(record.project_id ?? record.projectId, "RUN_EVENT_PROJECT_REQUIRED"),
    occurredAt: requiredString(record.occurred_at ?? record.occurredAt, "RUN_EVENT_TIME_REQUIRED"),
    payload,
  };
}

export function selectionClientContext(selection: CanvasSelectionContext | null): Record<string, unknown> {
  if (!selection || selection.nodeIds.length === 0) return {};
  if (!Number.isInteger(selection.documentVersion) || selection.documentVersion < 1) throw new Error("CANVAS_SELECTION_VERSION_INVALID");
  const nodeIds = [...new Set(selection.nodeIds.map((item) => item.trim()).filter(Boolean))];
  return { selected_node_ids: nodeIds, design_document_version: selection.documentVersion };
}

function parseInterrupt(value: unknown): RunInterrupt {
  const record = asRecord(value, "RUN_INTERRUPT_INVALID");
  return {
    id: requiredString(record.id, "RUN_INTERRUPT_ID_REQUIRED"),
    kind: requiredString(record.kind, "RUN_INTERRUPT_KIND_REQUIRED"),
    node: optionalString(record.node),
    resumable: typeof record.resumable === "boolean" ? record.resumable : true,
  };
}

function assertPublicPayload(value: unknown): void {
  if (Array.isArray(value)) { value.forEach(assertPublicPayload); return; }
  if (!value || typeof value !== "object") return;
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    if (FORBIDDEN_PUBLIC_KEYS.has(key)) throw new Error("RUN_EVENT_PRIVATE_FIELD_FORBIDDEN");
    assertPublicPayload(child);
  }
}

function asRecord(value: unknown, code: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(code);
  return value as Record<string, unknown>;
}
function requiredString(value: unknown, code: string): string { if (typeof value !== "string" || value.trim() === "") throw new Error(code); return value; }
function optionalString(value: unknown): string | null | undefined { if (value === undefined || value === null) return value; if (typeof value !== "string") throw new Error("OPTIONAL_STRING_INVALID"); return value; }
function arrayValue(value: unknown, code: string): unknown[] { if (!Array.isArray(value)) throw new Error(code); return value; }
function stringArray(value: unknown, code: string): string[] { const items = arrayValue(value, code); if (!items.every((item) => typeof item === "string")) throw new Error(code); return items as string[]; }
function requiredInteger(value: unknown, code: string, minimum: number): number { if (!Number.isInteger(value) || (value as number) < minimum) throw new Error(code); return value as number; }
function optionalInteger(value: unknown, fallback: number): number { if (value === undefined || value === null) return fallback; if (!Number.isInteger(value) || (value as number) < 0) throw new Error("OPTIONAL_INTEGER_INVALID"); return value as number; }