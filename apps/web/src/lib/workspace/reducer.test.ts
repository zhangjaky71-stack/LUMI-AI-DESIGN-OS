import { describe, expect, it } from "vitest";

import { exactArtifact, initialWorkspaceRuntimeState, reduceWorkspaceEvent } from "./reducer";
import type { SafeRunEvent } from "./types";

function event(eventId: string, eventType: SafeRunEvent["eventType"], payload: Record<string, unknown>): SafeRunEvent {
  return { eventId, eventType, agentRunId: "run-1", projectId: "project-1", occurredAt: "2026-08-18T00:00:00Z", payload };
}

describe("workspace event reducer", () => {
  it("deduplicates replayed event ids", () => {
    const first = event("evt-1", "agent.status", { message: "Working" });
    const once = reduceWorkspaceEvent(initialWorkspaceRuntimeState(), first);
    const twice = reduceWorkspaceEvent(once, first);
    expect(twice.timeline).toHaveLength(1);
    expect(twice.lastEventId).toBe("evt-1");
  });

  it("admits artifact cards only with an exact artifact version", () => {
    const state = reduceWorkspaceEvent(initialWorkspaceRuntimeState(), event("evt-2", "artifact.created", { artifact_id: "artifact-1", artifact_version_id: "version-7", version_number: 7 }));
    expect(state.artifacts).toEqual([{ artifactId: "artifact-1", artifactVersionId: "version-7", versionNumber: 7 }]);
    expect(state.timeline[0]?.type).toBe("artifact");
    expect(state.timeline[0]?.status).toBe("completed");
  });

  it("refuses to fabricate a link for artifact-only events", () => {
    const state = reduceWorkspaceEvent(initialWorkspaceRuntimeState(), event("evt-3", "artifact.created", { artifact_id: "artifact-1" }));
    expect(state.artifacts).toHaveLength(0);
    expect(state.timeline[0]?.type).toBe("artifact");
    expect(state.timeline[0]?.status).toBe("failed");
    expect(exactArtifact({ artifact_id: "artifact-1" })).toBeNull();
  });
});