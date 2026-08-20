import { describe, expect, it } from "vitest";

import {
  artifactUiPropagationSourceTimestamp,
  scheduleArtifactUiPropagationAfterPaint,
  type WorkspaceUiPropagationSample,
} from "./performance-telemetry";
import type { WorkspaceEvent } from "./types";

const sourceCreatedAt = "2026-08-20T10:00:00.000Z";

function artifactEvent(createdAt = sourceCreatedAt): WorkspaceEvent {
  return {
    id: "run-1:artifact:1",
    sequence: 3,
    run_id: "run-1",
    type: "artifact.created",
    artifact: {
      artifact_id: "artifact-1",
      version_id: "artifact-version-1",
      version: 1,
      title: "Direction A",
      media_type: "image/png",
      preview_label: "4:5",
      created_at: createdAt,
    },
    message: {
      id: "message-1",
      kind: "ARTIFACT",
      created_at: createdAt,
      text: "Artifact ready",
      run_id: "run-1",
      artifact_version_id: "artifact-version-1",
      approval_id: null,
      warning_code: null,
    },
  };
}

function messageEvent(): WorkspaceEvent {
  return {
    id: "run-1:message:1",
    sequence: 1,
    run_id: "run-1",
    type: "message.created",
    message: {
      id: "message-status-1",
      kind: "STATUS",
      created_at: sourceCreatedAt,
      text: "Working",
      run_id: "run-1",
      artifact_version_id: null,
      approval_id: null,
      warning_code: null,
    },
  };
}

describe("workspace UI propagation telemetry", () => {
  it("records artifact propagation only after two rendered frames", () => {
    const callbacks: FrameRequestCallback[] = [];
    const samples: WorkspaceUiPropagationSample[] = [];
    const sourceMs = Date.parse(sourceCreatedAt);
    const scheduled = scheduleArtifactUiPropagationAfterPaint(artifactEvent(), "task-image-1", {
      sink: (sample) => samples.push(sample),
      request_frame: (callback) => {
        callbacks.push(callback);
        return callbacks.length;
      },
      now_ms: () => sourceMs + 125,
    });

    expect(scheduled).toBe(true);
    expect(samples).toEqual([]);
    expect(callbacks).toHaveLength(1);
    callbacks.shift()?.(0);
    expect(samples).toEqual([]);
    expect(callbacks).toHaveLength(1);
    callbacks.shift()?.(16.7);

    expect(samples).toEqual([
      {
        schema_version: 1,
        event_id: "run-1:artifact:1",
        run_id: "run-1",
        task_id: "task-image-1",
        event_type: "artifact.created",
        source_created_at: sourceCreatedAt,
        source_created_at_unix_ms: sourceMs,
        painted_at_unix_ms: sourceMs + 125,
        duration_ms: 125,
      },
    ]);
  });

  it("does not fabricate propagation for uncorrelated workspace events", () => {
    const samples: WorkspaceUiPropagationSample[] = [];
    expect(
      scheduleArtifactUiPropagationAfterPaint(messageEvent(), "task-image-1", {
        sink: (sample) => samples.push(sample),
      }),
    ).toBe(false);
    expect(scheduleArtifactUiPropagationAfterPaint(artifactEvent(), null, { sink: () => undefined })).toBe(
      false,
    );
    expect(samples).toEqual([]);
    expect(artifactUiPropagationSourceTimestamp(messageEvent())).toBeNull();
  });

  it("fails closed when the canonical timestamp is invalid", () => {
    expect(() =>
      scheduleArtifactUiPropagationAfterPaint(artifactEvent("not-a-time"), "task-image-1", {
        sink: () => undefined,
      }),
    ).toThrowError("PERFORMANCE_UI_PROPAGATION_SOURCE_TIMESTAMP_INVALID");
  });

  it("fails closed when the browser clock precedes the canonical event", () => {
    const callbacks: FrameRequestCallback[] = [];
    const sourceMs = Date.parse(sourceCreatedAt);
    scheduleArtifactUiPropagationAfterPaint(artifactEvent(), "task-image-1", {
      sink: () => undefined,
      request_frame: (callback) => {
        callbacks.push(callback);
        return callbacks.length;
      },
      now_ms: () => sourceMs - 1,
    });
    callbacks.shift()?.(0);
    expect(() => callbacks.shift()?.(16.7)).toThrowError("PERFORMANCE_UI_PROPAGATION_CLOCK_REVERSAL");
  });
});
