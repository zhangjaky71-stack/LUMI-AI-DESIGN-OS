import { describe, expect, it } from "vitest";
import type { DesignDocument } from "../../design-ir/src/index";
import { CanvasOperationGateway } from "../src/index";

function document(): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "doc-node55",
    unit: "px",
    root_id: "root",
    nodes: {
      root: {
        id: "root",
        kind: "DOCUMENT_ROOT",
        parent_id: null,
        children: ["shape"],
      },
      shape: {
        id: "shape",
        kind: "SHAPE",
        parent_id: "root",
        children: [],
        transform: { x: 10, y: 20, width: 100, height: 80 },
      },
    },
    resources: {},
    metadata: { document_version: 1, applied_operation_ids: [] },
  };
}

describe("NODE-55 Canvas committed operation hook", () => {
  it("emits only descriptors that passed local Design IR execution", () => {
    const committed: string[] = [];
    const gateway = new CanvasOperationGateway(
      document(),
      undefined,
      (descriptors) => committed.push(...descriptors.map((item) => item.type)),
    );

    expect(
      gateway.commit({
        type: "MOVE_NODE",
        targetIds: ["shape"],
        payload: { x: 42, y: 55 },
      }).ok,
    ).toBe(true);
    expect(committed).toEqual(["MOVE_NODE"]);

    expect(
      gateway.commit({
        type: "MOVE_NODE",
        targetIds: ["missing"],
        payload: { x: 1, y: 2 },
      }).ok,
    ).toBe(false);
    expect(committed).toEqual(["MOVE_NODE"]);
  });

  it("emits a successful batch once with the original descriptor sequence", () => {
    const batches: string[][] = [];
    const gateway = new CanvasOperationGateway(
      document(),
      undefined,
      (descriptors) => batches.push(descriptors.map((item) => item.type)),
    );

    expect(
      gateway.commitBatch([
        {
          type: "MOVE_NODE",
          targetIds: ["shape"],
          payload: { x: 22, y: 33 },
        },
        {
          type: "RESIZE_NODE",
          targetIds: ["shape"],
          payload: { width: 120, height: 90 },
        },
      ]).ok,
    ).toBe(true);
    expect(batches).toEqual([["MOVE_NODE", "RESIZE_NODE"]]);
  });
});
