import { describe, expect, it } from "vitest";

import { parseRunControlSnapshot, parseSafeRunEvent, selectionClientContext } from "./types";

function safeEvent(payload: Record<string, unknown>) {
  return {
    event_id: "evt-1",
    event_type: "agent.delta",
    agent_run_id: "run-1",
    project_id: "project-1",
    occurred_at: "2026-08-18T00:00:00Z",
    payload,
  };
}

describe("workspace public contracts", () => {
  it("rejects private reasoning recursively", () => {
    expect(() => parseSafeRunEvent(safeEvent({ nested: { reasoning: "private" } }))).toThrow("RUN_EVENT_PRIVATE_FIELD_FORBIDDEN");
  });

  it("rejects secret-like public event keys before reducer ingestion", () => {
    expect(() => parseSafeRunEvent(safeEvent({ nested: { provider_api_key: "secret" } }))).toThrow("RUN_EVENT_PRIVATE_FIELD_FORBIDDEN");
    expect(() => parseSafeRunEvent(safeEvent({ authorization: "Bearer secret" }))).toThrow("RUN_EVENT_PRIVATE_FIELD_FORBIDDEN");
  });

  it("preserves canonical task identity for observability", () => {
    const control = parseRunControlSnapshot({
      agent_run_id: "run-1",
      project_id: "project-1",
      task_id: "task-1",
      thread_id: "thread-1",
      graph_key: "design",
      graph_version: "v1",
      code_git_sha: "abc",
      status: "running",
      resume_version: 1,
      next_nodes: ["research"],
      interrupts: [],
      context_refs: [],
      artifact_refs: [],
      updated_at: "2026-08-18T00:00:00Z",
    });
    expect(control.taskId).toBe("task-1");
  });

  it("serializes selected nodes with the exact document version", () => {
    expect(selectionClientContext({ documentVersion: 17, nodeIds: ["hero", "cta", "hero", "  "] })).toEqual({ selected_node_ids: ["hero", "cta"], design_document_version: 17 });
  });

  it("does not invent selection context", () => {
    expect(selectionClientContext(null)).toEqual({});
  });
});