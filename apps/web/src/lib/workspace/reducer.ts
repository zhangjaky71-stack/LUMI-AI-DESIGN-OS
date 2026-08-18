import type {
  ExactArtifactRef,
  RunControlSnapshot,
  SafeRunEvent,
} from "@/lib/workspace/types";

export type WorkspaceTimelineItem = {
  id: string;
  kind: "status" | "delta" | "progress" | "approval" | "artifact" | "warning";
  text: string;
  occurredAt: string;
};

export type WorkspaceRuntimeState = {
  control: RunControlSnapshot | null;
  timeline: readonly WorkspaceTimelineItem[];
  artifacts: readonly ExactArtifactRef[];
  seenEventIds: ReadonlySet<string>;
  lastEventId: string | null;
};

export function initialWorkspaceRuntimeState(
  control: RunControlSnapshot | null = null,
): WorkspaceRuntimeState {
  return {
    control,
    timeline: [],
    artifacts: [],
    seenEventIds: new Set(),
    lastEventId: null,
  };
}

export function replaceCanonicalControl(
  state: WorkspaceRuntimeState,
  control: RunControlSnapshot,
): WorkspaceRuntimeState {
  return { ...state, control };
}

export function reduceWorkspaceEvent(
  state: WorkspaceRuntimeState,
  event: SafeRunEvent,
): WorkspaceRuntimeState {
  if (state.seenEventIds.has(event.eventId)) return state;
  const seenEventIds = new Set(state.seenEventIds);
  seenEventIds.add(event.eventId);
  const timeline = [...state.timeline];
  const artifacts = [...state.artifacts];
  const item = timelineItem(event);
  if (item) timeline.push(item);

  if (event.eventType === "artifact.created") {
    const artifact = exactArtifact(event.payload);
    if (artifact && !artifacts.some((item) => item.artifactVersionId === artifact.artifactVersionId)) {
      artifacts.push(artifact);
    }
  }

  return {
    ...state,
    timeline: timeline.slice(-250),
    artifacts,
    seenEventIds,
    lastEventId: event.eventId,
  };
}

export function exactArtifact(payload: Readonly<Record<string, unknown>>): ExactArtifactRef | null {
  const artifactId = stringValue(payload.artifact_id ?? payload.artifactId);
  const artifactVersionId = stringValue(
    payload.artifact_version_id ?? payload.artifactVersionId,
  );
  if (!artifactId || !artifactVersionId) return null;
  const versionRaw = payload.version_number ?? payload.versionNumber;
  const versionNumber = Number.isInteger(versionRaw) && (versionRaw as number) > 0
    ? (versionRaw as number)
    : undefined;
  return {
    artifactId,
    artifactVersionId,
    ...(versionNumber ? { versionNumber } : {}),
    ...(stringValue(payload.label) ? { label: stringValue(payload.label)! } : {}),
    ...(stringValue(payload.preview_ref ?? payload.previewRef)
      ? { previewRef: stringValue(payload.preview_ref ?? payload.previewRef)! }
      : {}),
  };
}

function timelineItem(event: SafeRunEvent): WorkspaceTimelineItem | null {
  const payload = event.payload;
  switch (event.eventType) {
    case "agent.delta": {
      const text = stringValue(payload.text ?? payload.delta);
      return text ? item(event, "delta", text) : null;
    }
    case "agent.status":
      return item(event, "status", stringValue(payload.message ?? payload.status) ?? "Agent status updated.");
    case "node.started":
      return item(event, "status", `Started ${stringValue(payload.node) ?? "next task"}.`);
    case "task.progress": {
      const message = stringValue(payload.message);
      const progress = numberValue(payload.progress);
      return item(
        event,
        "progress",
        message ?? (progress === null ? "Task progress updated." : `Task progress ${Math.round(progress * 100)}%.`),
      );
    }
    case "approval.required":
      return item(event, "approval", "Agent is waiting for your approval.");
    case "artifact.created": {
      const artifact = exactArtifact(payload);
      return item(
        event,
        artifact ? "artifact" : "warning",
        artifact
          ? `Created artifact version ${artifact.versionNumber ?? artifact.artifactVersionId}.`
          : "Artifact event omitted an exact artifact version and was not linked.",
      );
    }
    case "run.started":
      return item(event, "status", "Agent run started.");
    case "run.completed":
      return item(event, "status", "Agent run completed.");
    case "run.cancelled":
      return item(event, "warning", "Agent run cancelled. External side effects may already exist.");
    case "run.waiting_external":
      return item(event, "status", "Waiting for an external job to finish.");
    case "tool.call":
      return item(event, "status", `Using ${stringValue(payload.tool_name ?? payload.tool) ?? "a tool"}.`);
    default:
      return null;
  }
}

function item(
  event: SafeRunEvent,
  kind: WorkspaceTimelineItem["kind"],
  text: string,
): WorkspaceTimelineItem {
  return { id: event.eventId, kind, text, occurredAt: event.occurredAt };
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
