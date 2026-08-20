import type { WorkspaceEvent } from "./types";

export interface WorkspaceUiPropagationSample {
  readonly schema_version: 1;
  readonly event_id: string;
  readonly run_id: string;
  readonly task_id: string;
  readonly event_type: "artifact.created";
  readonly source_created_at: string;
  readonly source_created_at_unix_ms: number;
  readonly painted_at_unix_ms: number;
  readonly duration_ms: number;
}

export type WorkspaceUiPropagationSink = (sample: WorkspaceUiPropagationSample) => void;

declare global {
  interface Window {
    __LUMI_PERFORMANCE_UI_PROPAGATION_SINK__?: WorkspaceUiPropagationSink;
  }
}

interface ScheduleOptions {
  readonly sink?: WorkspaceUiPropagationSink;
  readonly request_frame?: (callback: FrameRequestCallback) => number;
  readonly now_ms?: () => number;
}

/**
 * The UI propagation clock starts from the canonical artifact event's user-facing
 * message timestamp. Other workspace event types do not currently expose a safe,
 * task-correlated canonical event timestamp and are intentionally not measured.
 */
export function artifactUiPropagationSourceTimestamp(event: WorkspaceEvent): string | null {
  return event.type === "artifact.created" ? event.message.created_at : null;
}

export function scheduleArtifactUiPropagationAfterPaint(
  event: WorkspaceEvent,
  taskId: string | null,
  options: ScheduleOptions = {},
): boolean {
  if (event.type !== "artifact.created" || !taskId) return false;
  const sourceCreatedAt = artifactUiPropagationSourceTimestamp(event);
  if (!sourceCreatedAt) return false;

  const sink =
    options.sink ??
    (typeof window === "undefined" ? undefined : window.__LUMI_PERFORMANCE_UI_PROPAGATION_SINK__);
  if (!sink) return false;

  const sourceCreatedAtUnixMs = Date.parse(sourceCreatedAt);
  if (!Number.isSafeInteger(sourceCreatedAtUnixMs) || sourceCreatedAtUnixMs < 0) {
    throw new Error("PERFORMANCE_UI_PROPAGATION_SOURCE_TIMESTAMP_INVALID");
  }

  const requestFrame = options.request_frame ?? globalThis.requestAnimationFrame.bind(globalThis);
  const nowMs = options.now_ms ?? Date.now;
  requestFrame(() => {
    requestFrame(() => {
      const paintedAtUnixMs = nowMs();
      if (!Number.isSafeInteger(paintedAtUnixMs) || paintedAtUnixMs < sourceCreatedAtUnixMs) {
        throw new Error("PERFORMANCE_UI_PROPAGATION_CLOCK_REVERSAL");
      }
      sink({
        schema_version: 1,
        event_id: event.id,
        run_id: event.run_id,
        task_id: taskId,
        event_type: "artifact.created",
        source_created_at: sourceCreatedAt,
        source_created_at_unix_ms: sourceCreatedAtUnixMs,
        painted_at_unix_ms: paintedAtUnixMs,
        duration_ms: paintedAtUnixMs - sourceCreatedAtUnixMs,
      });
    });
  });
  return true;
}
