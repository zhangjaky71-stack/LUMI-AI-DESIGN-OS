import { describe, expect, it } from "vitest";
import type { DesignDocument } from "../../design-ir/src/index";
import { CanvasController, HeadlessRendererAdapter, type OperationDescriptor } from "../src/index";

function document(): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "node56-document",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["a", "b"] },
      a: { id: "a", kind: "SHAPE", parent_id: "root", children: [], opacity: 1, transform: { x: 10, y: 20, width: 100, height: 80 } },
      b: { id: "b", kind: "SHAPE", parent_id: "root", children: [], opacity: 1, transform: { x: 30, y: 40, width: 120, height: 90 } },
    },
    resources: {},
    metadata: { document_version: 1, applied_operation_ids: [] },
  };
}

describe("NODE-56 CanvasController batch surface", () => {
  it("commits multi-node inspector changes atomically and emits one descriptor batch", () => {
    const emitted: readonly OperationDescriptor[][] = [];
    const batches: OperationDescriptor[][] = [];
    const controller = new CanvasController(document(), new HeadlessRendererAdapter(), {
      onOperationCommitted: (descriptors) => batches.push([...descriptors]),
    });
    const result = controller.commitBatch([
      { type: "MOVE_NODE", targetIds: ["a"], payload: { x: 50, y: 20 }, reason: "inspector x" },
      { type: "MOVE_NODE", targetIds: ["b"], payload: { x: 50, y: 40 }, reason: "inspector x" },
    ]);
    expect(result.ok).toBe(true);
    expect(controller.document.nodes.a?.transform?.x).toBe(50);
    expect(controller.document.nodes.b?.transform?.x).toBe(50);
    expect(batches).toHaveLength(1);
    expect(batches[0]).toHaveLength(2);
    expect(emitted).toHaveLength(0);
  });
});