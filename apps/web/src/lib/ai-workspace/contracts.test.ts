import { describe, expect, it } from "vitest";
import { applyWorkspaceEvent, decodeSseFrame, isApprovalActionable } from "./contracts";
import type { AIWorkspaceSnapshot, WorkspaceEvent } from "./types";

function snapshot(): AIWorkspaceSnapshot {
  return {
    project_id: "project-1",
    project_name: "Project",
    brand_name: null,
    document: {
      document_id: "doc-1",
      version: 3,
      title: "Canvas",
      width: 1000,
      height: 1000,
      selection_options: [],
    },
    references: [],
    run: {
      run_id: "run-1",
      version: 2,
      status: "RUNNING",
      last_event_id: null,
      started_at: "2026-08-15T00:00:00.000Z",
      completed_at: null,
      selected_node_ids: [],
      document_version: 3,
      tasks: [],
    },
    messages: [],
    artifacts: [],
    approvals: [],
  };
}

describe("AI workspace realtime contracts", () => {
  it("decodes an SSE frame and rejects event/id mismatch", () => {
    const event: WorkspaceEvent = {
      id: "evt-1",
      sequence: 1,
      run_id: "run-1",
      type: "message.created",
      message: {
        id: "message-1",
        kind: "STATUS",
        created_at: "2026-08-15T00:00:01.000Z",
        text: "safe progress",
        run_id: "run-1",
        artifact_version_id: null,
        approval_id: null,
        warning_code: null,
      },
    };
    const frame = `id: evt-1\nevent: message.created\ndata: ${JSON.stringify(event)}`;
    expect(decodeSseFrame(frame)).toEqual(event);
    expect(() => decodeSseFrame(frame.replace("id: evt-1", "id: evt-other"))).toThrow();
  });

  it("deduplicates at-least-once realtime delivery by event id", () => {
    const base = snapshot();
    const event: WorkspaceEvent = {
      id: "run-1:2",
      sequence: 2,
      run_id: "run-1",
      type: "message.created",
      message: {
        id: "message-2",
        kind: "STATUS",
        created_at: "2026-08-15T00:00:02.000Z",
        text: "progress",
        run_id: "run-1",
        artifact_version_id: null,
        approval_id: null,
        warning_code: null,
      },
    };
    const once = applyWorkspaceEvent({ snapshot: base, seen_event_ids: [] }, event);
    const twice = applyWorkspaceEvent(once, event);
    expect(once.snapshot.messages).toHaveLength(1);
    expect(twice.snapshot.messages).toHaveLength(1);
    expect(twice.seen_event_ids).toEqual([event.id]);
    expect(twice.snapshot.run?.last_event_id).toBe(event.id);
  });

  it("makes an approval non-actionable when its run version is stale", () => {
    const base = snapshot();
    const approval = {
      approval_id: "approval-1",
      run_id: "run-1",
      expected_run_version: 1,
      state: "PENDING" as const,
      title: "Direction",
      description: "Approve?",
      impact: null,
      estimated_cost_microusd: null,
      artifact_version_ids: [],
      expires_at: null,
    };
    expect(isApprovalActionable(approval, base.run)).toBe(false);
    expect(isApprovalActionable({ ...approval, expected_run_version: 2 }, base.run)).toBe(true);
  });
});
