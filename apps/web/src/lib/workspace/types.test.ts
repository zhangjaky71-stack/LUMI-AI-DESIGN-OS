import { describe, expect, it } from "vitest";

import { parseSafeRunEvent, selectionClientContext } from "./types";

describe("workspace public contracts", () => {
  it("rejects private reasoning recursively", () => {
    expect(() =>
      parseSafeRunEvent({
        event_id: "evt-1",
        event_type: "agent.delta",
        agent_run_id: "run-1",
        project_id: "project-1",
        occurred_at: "2026-08-18T00:00:00Z",
        payload: { nested: { reasoning: "private" } },
      }),
    ).toThrow("RUN_EVENT_PRIVATE_FIELD_FORBIDDEN");
  });

  it("serializes selected nodes with the exact document version", () => {
    expect(
      selectionClientContext({
        documentVersion: 17,
        nodeIds: ["hero", "cta", "hero", "  "],
      }),
    ).toEqual({
      selected_node_ids: ["hero", "cta"],
      design_document_version: 17,
    });
  });

  it("does not invent selection context", () => {
    expect(selectionClientContext(null)).toEqual({});
  });
});
