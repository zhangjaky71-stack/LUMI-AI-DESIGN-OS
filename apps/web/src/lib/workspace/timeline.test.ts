import { describe, expect, it } from "vitest";

import { canonicalTimelineItem, eventTimelineItem } from "./timeline";
import type { RunControlSnapshot, SafeRunEvent } from "./types";

function event(eventType: SafeRunEvent["eventType"], payload: Record<string, unknown>): SafeRunEvent {
  return { eventId: `evt-${eventType}`, eventType, agentRunId: "run-1", projectId: "project-1", occurredAt: "2026-08-18T00:00:00Z", payload };
}

function control(overrides: Partial<RunControlSnapshot> = {}): RunControlSnapshot {
  return {
    agentRunId: "run-1",
    projectId: "project-1",
    taskId: "task-1",
    threadId: "thread-1",
    graphKey: "design",
    graphVersion: "v1",
    codeGitSha: "abc",
    status: "running",
    resumeVersion: 2,
    nextNodes: ["quality_check"],
    interrupts: [],
    contextRefs: [],
    artifactRefs: [],
    repairIteration: 0,
    maxRepairIterations: 3,
    updatedAt: "2026-08-18T00:01:00Z",
    ...overrides,
  };
}

describe("NODE-57 timeline projection", () => {
  it("recovers a meaningful current stage from canonical state without browser event history", () => {
    const item = canonicalTimelineItem(control());
    expect(item?.label).toBe("Quality Check");
    expect(item?.status).toBe("running");
    expect(item?.taskId).toBe("task-1");
  });

  it("makes approval canonical and visibly waiting after refresh", () => {
    const item = canonicalTimelineItem(control({ interrupts: [{ id: "approve-1", kind: "approval", node: "creative_review", resumable: true }] }));
    expect(item?.type).toBe("approval");
    expect(item?.status).toBe("waiting");
    expect(item?.safeSummary).toContain("Creative Review");
  });

  it("shows real count progress but never fabricates a percentage from an opaque progress scalar", () => {
    const counted = eventTimelineItem(event("task.progress", { current: 2, total: 4, message: "Generating directions" }));
    expect(counted?.progress).toEqual({ current: 2, total: 4 });
    const opaque = eventTimelineItem(event("task.progress", { progress: 0.63, message: "Working" }));
    expect(opaque?.progress).toBeUndefined();
  });

  it("surfaces retry/provider fallback only from explicit public summary fields", () => {
    const item = eventTimelineItem(event("tool.call", { tool_name: "image_generate", retrying: true, retry_attempt: 2, fallback_provider: "provider_b" }));
    expect(item?.label).toBe("Generated creative output");
    expect(item?.retrySummary).toContain("Retry 2");
    expect(item?.retrySummary).toContain("Provider B");
  });

  it("does not serialize unrelated payload fields into the visible timeline model", () => {
    const item = eventTimelineItem(event("tool.call", { tool_name: "web_search", message: "Searched market sources", debug_secret: "do-not-display" }));
    expect(JSON.stringify(item)).not.toContain("do-not-display");
    expect(item?.safeSummary).toBe("Searched market sources");
  });

  it("links artifacts only when an exact artifact version exists", () => {
    const item = eventTimelineItem(event("artifact.created", { artifact_id: "artifact-1", artifact_version_id: "version-3", version_number: 3 }));
    expect(item?.artifact?.artifactVersionId).toBe("version-3");
    expect(item?.status).toBe("completed");
    const incomplete = eventTimelineItem(event("artifact.created", { artifact_id: "artifact-1" }));
    expect(incomplete?.artifact).toBeUndefined();
    expect(incomplete?.status).toBe("failed");
  });

  it("shows canonical errors without stack traces", () => {
    const item = canonicalTimelineItem(control({ status: "failed", errorCode: "PROVIDER_TIMEOUT" }));
    expect(item?.type).toBe("error");
    expect(item?.errorCode).toBe("PROVIDER_TIMEOUT");
    expect(JSON.stringify(item)).not.toContain("stack");
  });
});