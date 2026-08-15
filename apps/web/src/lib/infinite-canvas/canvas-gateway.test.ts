import { describe, expect, it } from "vitest";
import { getDocumentVersion, type DesignDocument, type DesignOperation } from "@lumi/design-ir";
import { DeterministicInfiniteCanvasGateway } from "./canvas-gateway";
import type { InfiniteCanvasSeed } from "./types";

function document(version = 3): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "doc-1",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
      frame: {
        id: "frame",
        kind: "FRAME",
        parent_id: "root",
        children: ["shape"],
        transform: { x: 0, y: 0, width: 1000, height: 1000 },
      },
      shape: {
        id: "shape",
        kind: "SHAPE",
        parent_id: "frame",
        children: [],
        transform: { x: 10, y: 20, width: 100, height: 100 },
      },
    },
    resources: {},
    metadata: { document_version: version },
  };
}

function seed(conflict = false): InfiniteCanvasSeed {
  return {
    snapshot: { project_id: "project-1", document: document(), saved_at: "2026-08-15T00:00:00.000Z" },
    conflict_on_next_save: conflict,
  };
}

function move(version: number): DesignOperation {
  return {
    operation_id: `move-${version}`,
    type: "MOVE_NODE",
    target_ids: ["shape"],
    expected_document_version: version,
    payload: { x: 50, y: 80 },
  };
}

describe("DeterministicInfiniteCanvasGateway", () => {
  it("applies a batched transaction and advances document version once", async () => {
    const gateway = new DeterministicInfiniteCanvasGateway(seed());
    const saved = await gateway.saveOperations("org-lumi", {
      project_id: "project-1",
      document_id: "doc-1",
      expected_document_version: 3,
      operations: [
        move(3),
        {
          operation_id: "resize",
          type: "RESIZE_NODE",
          target_ids: ["shape"],
          expected_document_version: 3,
          payload: { width: 180, height: 160 },
        },
      ],
    });
    expect(getDocumentVersion(saved.document)).toBe(4);
    expect(saved.document.nodes.shape?.transform?.x).toBe(50);
    expect(saved.document.nodes.shape?.transform?.width).toBe(180);
  });

  it("rejects stale saves after a canonical external edit", async () => {
    const gateway = new DeterministicInfiniteCanvasGateway(seed(true));
    await expect(
      gateway.saveOperations("org-lumi", {
        project_id: "project-1",
        document_id: "doc-1",
        expected_document_version: 3,
        operations: [move(3)],
      }),
    ).rejects.toMatchObject({ problem: { code: "DOCUMENT_VERSION_CONFLICT" } });
    const canonical = await gateway.getDocument("org-lumi", "project-1");
    expect(getDocumentVersion(canonical.document)).toBe(4);
  });

  it("rejects mixed operation versions inside one autosave transaction", async () => {
    const gateway = new DeterministicInfiniteCanvasGateway(seed());
    await expect(
      gateway.saveOperations("org-lumi", {
        project_id: "project-1",
        document_id: "doc-1",
        expected_document_version: 3,
        operations: [move(4)],
      }),
    ).rejects.toMatchObject({ problem: { code: "DESIGN_OPERATION_VERSION_MISMATCH" } });
  });
});
