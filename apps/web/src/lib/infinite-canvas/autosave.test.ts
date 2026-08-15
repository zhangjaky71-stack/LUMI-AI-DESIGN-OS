import { describe, expect, it } from "vitest";
import type { DesignOperation } from "@lumi/design-ir";
import { CanvasAutosaveBuffer, rebaseOperationsVersion } from "./autosave";

function move(id: string, version: number, x: number): DesignOperation {
  return {
    operation_id: `move-${id}-${version}`,
    type: "MOVE_NODE",
    target_ids: [id],
    expected_document_version: version,
    payload: { x, y: 0 },
  };
}

describe("CanvasAutosaveBuffer", () => {
  it("rebases multiple local transactions to one server document version", () => {
    const buffer = new CanvasAutosaveBuffer();
    buffer.append(7, [move("a", 7, 10)]);
    buffer.append(7, [move("a", 8, 20)]);
    const batch = buffer.snapshot();
    expect(batch?.base_document_version).toBe(7);
    expect(batch?.operations).toHaveLength(2);
    expect(batch?.operations.every((operation) => operation.expected_document_version === 7)).toBe(true);
  });

  it("acknowledges only the flushed prefix and rebases operations queued during save", () => {
    const buffer = new CanvasAutosaveBuffer();
    buffer.append(3, [move("a", 3, 10), move("b", 3, 20)]);
    const inFlight = buffer.snapshot()!;
    buffer.append(3, [move("c", 4, 30)]);
    buffer.acknowledge(inFlight.count, 4);
    const remaining = buffer.snapshot();
    expect(remaining?.base_document_version).toBe(4);
    expect(remaining?.operations).toHaveLength(1);
    expect(remaining?.operations[0]?.expected_document_version).toBe(4);
  });

  it("rehydrates nested BATCH operations to the same transaction version", () => {
    const nested: DesignOperation = {
      operation_id: "batch",
      type: "BATCH",
      target_ids: [],
      expected_document_version: 2,
      payload: { operations: [move("a", 9, 20)] },
    };
    const [rebased] = rebaseOperationsVersion([nested], 5);
    expect(rebased?.expected_document_version).toBe(5);
    const child = (rebased?.payload.operations as DesignOperation[] | undefined)?.[0];
    expect(child?.expected_document_version).toBe(5);
  });
});
