import { eventTimelineItem, type WorkspaceTimelineItem } from "@/lib/workspace/timeline";
import type { ExactArtifactRef, RunControlSnapshot, SafeRunEvent } from "@/lib/workspace/types";

export type WorkspaceRuntimeState = {
  control: RunControlSnapshot | null;
  timeline: readonly WorkspaceTimelineItem[];
  artifacts: readonly ExactArtifactRef[];
  seenEventIds: ReadonlySet<string>;
  lastEventId: string | null;
};

export function initialWorkspaceRuntimeState(control: RunControlSnapshot | null = null): WorkspaceRuntimeState {
  return { control, timeline: [], artifacts: [], seenEventIds: new Set(), lastEventId: null };
}

export function replaceCanonicalControl(state: WorkspaceRuntimeState, control: RunControlSnapshot): WorkspaceRuntimeState {
  return { ...state, control };
}

export function reduceWorkspaceEvent(state: WorkspaceRuntimeState, event: SafeRunEvent): WorkspaceRuntimeState {
  if (state.seenEventIds.has(event.eventId)) return state;
  const seenEventIds = new Set(state.seenEventIds);
  seenEventIds.add(event.eventId);
  const timeline = [...state.timeline];
  const artifacts = [...state.artifacts];
  const item = eventTimelineItem(event);
  if (item) timeline.push(item);

  if (item?.artifact && !artifacts.some((artifact) => artifact.artifactVersionId === item.artifact!.artifactVersionId)) {
    artifacts.push(item.artifact);
  }

  return { ...state, timeline: timeline.slice(-250), artifacts, seenEventIds, lastEventId: event.eventId };
}

export function exactArtifact(payload: Readonly<Record<string, unknown>>): ExactArtifactRef | null {
  const artifactId = stringValue(payload.artifact_id ?? payload.artifactId);
  const artifactVersionId = stringValue(payload.artifact_version_id ?? payload.artifactVersionId);
  if (!artifactId || !artifactVersionId) return null;
  const versionRaw = payload.version_number ?? payload.versionNumber;
  const versionNumber = Number.isInteger(versionRaw) && (versionRaw as number) > 0 ? versionRaw as number : undefined;
  const label = stringValue(payload.label);
  const previewRef = stringValue(payload.preview_ref ?? payload.previewRef);
  return {
    artifactId,
    artifactVersionId,
    ...(versionNumber ? { versionNumber } : {}),
    ...(label ? { label } : {}),
    ...(previewRef ? { previewRef } : {}),
  };
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}