import { LumiApiError } from "@/lib/app-shell/api-client";
import { scheduleArtifactUiPropagationAfterPaint } from "./performance-telemetry";
import type {
  AIWorkspaceSnapshot,
  AgentRunSnapshot,
  ApprovalDecisionInput,
  StartRunInput,
  WorkspaceApproval,
  WorkspaceEvent,
  WorkspaceMessage,
  WorkspaceReducerState,
} from "./types";

export function workspaceProblem(code: string, status = 409): LumiApiError {
  return new LumiApiError({
    type: `https://errors.lumi.dev/ai-workspace/${code.toLowerCase().replaceAll("_", "-")}`,
    title: code,
    status,
    code,
    request_id: `workspace-${code.toLowerCase()}`,
  });
}

export function validateStartRunInput(input: StartRunInput): StartRunInput {
  const prompt = input.prompt.trim();
  if (!prompt) throw workspaceProblem("PROMPT_REQUIRED", 400);
  if (prompt.length > 12_000) throw workspaceProblem("PROMPT_TOO_LONG", 400);
  if (!Number.isSafeInteger(input.document_version) || input.document_version < 1) {
    throw workspaceProblem("DOCUMENT_VERSION_INVALID", 400);
  }
  const selected = [...new Set(input.selected_node_ids.map((value) => value.trim()).filter(Boolean))];
  const refs = [...new Set(input.reference_asset_ids.map((value) => value.trim()).filter(Boolean))];
  const artifactRefs = [
    ...new Set(input.reference_artifact_version_ids.map((value) => value.trim()).filter(Boolean)),
  ];
  return {
    ...input,
    prompt,
    selected_node_ids: selected,
    reference_asset_ids: refs,
    reference_artifact_version_ids: artifactRefs,
  };
}

export function isApprovalExpired(approval: WorkspaceApproval, now = Date.now()): boolean {
  if (!approval.expires_at) return false;
  const timestamp = Date.parse(approval.expires_at);
  return Number.isFinite(timestamp) && timestamp <= now;
}

export function isApprovalActionable(
  approval: WorkspaceApproval,
  run: AgentRunSnapshot | null,
  now = Date.now(),
): boolean {
  return (
    approval.state === "PENDING" &&
    run !== null &&
    approval.run_id === run.run_id &&
    approval.expected_run_version === run.version &&
    !isApprovalExpired(approval, now)
  );
}

export function validateApprovalDecision(
  input: ApprovalDecisionInput,
  approval: WorkspaceApproval,
  run: AgentRunSnapshot | null,
  now = Date.now(),
): ApprovalDecisionInput {
  if (input.approval_id !== approval.approval_id || input.run_id !== approval.run_id) {
    throw workspaceProblem("APPROVAL_NOT_FOUND", 404);
  }
  if (
    !isApprovalActionable(approval, run, now) ||
    input.expected_run_version !== approval.expected_run_version
  ) {
    throw workspaceProblem("APPROVAL_STALE", 409);
  }
  const note = input.request_changes_note?.trim() || null;
  if (input.decision === "REQUEST_CHANGES" && !note) {
    throw workspaceProblem("REQUEST_CHANGES_NOTE_REQUIRED", 400);
  }
  return { ...input, request_changes_note: note };
}

function upsertById<T>(
  values: readonly T[],
  next: T,
  idOf: (value: T) => string,
): readonly T[] {
  const id = idOf(next);
  const index = values.findIndex((value) => idOf(value) === id);
  if (index < 0) return [...values, next];
  return values.map((value, current) => (current === index ? next : value));
}

function upsertMessage(
  values: readonly WorkspaceMessage[],
  message: WorkspaceMessage,
): readonly WorkspaceMessage[] {
  return upsertById(values, message, (value) => value.id);
}

function artifactTaskId(snapshot: AIWorkspaceSnapshot, event: WorkspaceEvent): string | null {
  if (event.type !== "artifact.created") return null;
  return (
    snapshot.run?.tasks.find((task) =>
      task.artifact_version_ids?.includes(event.artifact.version_id),
    )?.task_id ?? null
  );
}

export function applyWorkspaceEvent(
  state: WorkspaceReducerState,
  event: WorkspaceEvent,
): WorkspaceReducerState {
  if (state.seen_event_ids.includes(event.id)) return state;
  if (state.snapshot.run && state.snapshot.run.run_id !== event.run_id) return state;

  let snapshot: AIWorkspaceSnapshot = state.snapshot;
  if (event.type === "run.status") {
    snapshot = { ...snapshot, run: event.run };
  } else if (event.type === "message.created") {
    snapshot = { ...snapshot, messages: upsertMessage(snapshot.messages, event.message) };
  } else if (event.type === "artifact.created") {
    snapshot = {
      ...snapshot,
      artifacts: upsertById(snapshot.artifacts, event.artifact, (value) => value.version_id),
      messages: upsertMessage(snapshot.messages, event.message),
    };
  } else {
    snapshot = {
      ...snapshot,
      approvals: upsertById(snapshot.approvals, event.approval, (value) => value.approval_id),
      messages: upsertMessage(snapshot.messages, event.message),
    };
  }

  if (snapshot.run?.run_id === event.run_id) {
    snapshot = {
      ...snapshot,
      run: { ...snapshot.run, last_event_id: event.id },
    };
  }

  scheduleArtifactUiPropagationAfterPaint(event, artifactTaskId(snapshot, event));
  return {
    snapshot,
    seen_event_ids: [...state.seen_event_ids.slice(-255), event.id],
  };
}

export function decodeSseFrame(frame: string): WorkspaceEvent | null {
  let id = "";
  let eventType = "";
  const data: string[] = [];
  for (const raw of frame.replaceAll("\r\n", "\n").split("\n")) {
    if (!raw || raw.startsWith(":")) continue;
    const separator = raw.indexOf(":");
    const field = separator < 0 ? raw : raw.slice(0, separator);
    const value = separator < 0 ? "" : raw.slice(separator + 1).replace(/^ /, "");
    if (field === "id") id = value;
    if (field === "event") eventType = value;
    if (field === "data") data.push(value);
  }
  if (!data.length) return null;
  const parsed = JSON.parse(data.join("\n")) as WorkspaceEvent;
  if (!parsed || typeof parsed !== "object" || typeof parsed.id !== "string") {
    throw workspaceProblem("STREAM_EVENT_INVALID", 502);
  }
  if (id && parsed.id !== id) throw workspaceProblem("STREAM_EVENT_ID_MISMATCH", 502);
  if (eventType && parsed.type !== eventType) throw workspaceProblem("STREAM_EVENT_TYPE_MISMATCH", 502);
  return parsed;
}
