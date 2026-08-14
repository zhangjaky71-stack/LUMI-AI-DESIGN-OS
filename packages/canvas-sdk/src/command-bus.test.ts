import { describe, expect, it } from "vitest";

import type { DesignDocument, DesignOperation } from "../../design-ir/src/index";
import type { DesignConstraint } from "../../design-constraints/src/index";
import { CanvasCommandBus } from "./command-bus";

function fixture(): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "history-doc",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["node"] },
      node: {
        id: "node",
        kind: "SHAPE",
        parent_id: "root",
        children: [],
        transform: { x: 0, y: 0, width: 100, height: 100 },
      },
    },
    resources: {},
    metadata: { document_version: 1 },
  };
}

function move(): DesignOperation {
  return {
    operation_id: "move-node",
    type: "MOVE_NODE",
    target_ids: ["node"],
    expected_document_version: 1,
    payload: { x: 40, y: 10 },
  };
}

describe("CanvasCommandBus", () => {
  it("replays undo/redo as fresh Design Operations", () => {
    const bus = new CanvasCommandBus(fixture());
    expect(bus.dispatch("move", [move()], []).accepted).toBe(true);
    expect(bus.document.nodes.node?.transform?.x).toBe(40);
    expect(bus.undo([]).accepted).toBe(true);
    expect(bus.document.nodes.node?.transform?.x).toBe(0);
    expect(bus.redo([]).accepted).toBe(true);
    expect(bus.document.nodes.node?.transform?.x).toBe(40);
  });

  it("cannot use undo to bypass a newly active hard constraint", () => {
    const bus = new CanvasCommandBus(fixture());
    expect(bus.dispatch("move", [move()], []).accepted).toBe(true);
    const lock: DesignConstraint = {
      id: "lock-current-position",
      type: "LOCK_POSITION",
      scope: { node_ids: ["node"] },
      severity: "HARD",
      source: "USER_EXPLICIT",
      priority: 1000,
      parameters: {},
      active: true,
      document_version: 2,
    };
    const undo = bus.undo([lock]);
    expect(undo.accepted).toBe(false);
    expect(undo.guarded.preflight.decision).toBe("DENY");
    expect(bus.document.nodes.node?.transform?.x).toBe(40);
    expect(bus.canUndo).toBe(true);
  });
});
