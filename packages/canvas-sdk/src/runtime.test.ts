import { describe, expect, it } from "vitest";

import type { DesignDocument } from "../../design-ir/src/index";
import type { DesignConstraint } from "../../design-constraints/src/index";
import { CanvasController } from "./controller";
import { applyMatrix, transformToMatrix } from "./matrix";
import { projectDesignDocument } from "./ir-scene";
import { CanvasSelectionModel } from "./selection";
import { CanvasSpatialIndex } from "./spatial-index";

function documentFixture(): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "canvas-doc",
    unit: "px",
    root_id: "root",
    nodes: {
      root: {
        id: "root",
        kind: "DOCUMENT_ROOT",
        parent_id: null,
        children: ["frame-a", "frame-b"],
      },
      "frame-a": {
        id: "frame-a",
        kind: "FRAME",
        parent_id: "root",
        children: ["text", "shape", "locked"],
        transform: { x: 100, y: 50, width: 400, height: 300 },
      },
      text: {
        id: "text",
        kind: "TEXT",
        parent_id: "frame-a",
        children: [],
        transform: { x: 10, y: 20, width: 160, height: 40 },
        content: "你好 LUMI",
      },
      shape: {
        id: "shape",
        kind: "SHAPE",
        parent_id: "frame-a",
        children: [],
        transform: { x: 220, y: 80, width: 80, height: 60 },
      },
      locked: {
        id: "locked",
        kind: "IMAGE",
        parent_id: "frame-a",
        children: [],
        locked: true,
        asset_id: "asset-product",
        transform: { x: 30, y: 150, width: 120, height: 100 },
      },
      "frame-b": {
        id: "frame-b",
        kind: "FRAME",
        parent_id: "root",
        children: [],
        transform: { x: 700, y: 100, width: 300, height: 300 },
      },
    },
    resources: {},
    metadata: { document_version: 3 },
  };
}

describe("NODE-40 Design IR scene projection", () => {
  it("uses degree-based affine transforms and nested world coordinates", () => {
    const point = applyMatrix(transformToMatrix({ rotation_deg: 90 }), { x: 10, y: 0 });
    expect(point.x).toBeCloseTo(0, 8);
    expect(point.y).toBeCloseTo(10, 8);

    const scene = projectDesignDocument(documentFixture());
    expect(scene.frame_ids).toEqual(["frame-a", "frame-b"]);
    expect(scene.nodes.get("text")?.world_bounds.x).toBeCloseTo(110, 8);
    expect(scene.nodes.get("text")?.world_bounds.y).toBeCloseTo(70, 8);
    expect(scene.diagnostics).toEqual([]);
  });

  it("supports topmost click, marquee and locked-node transform filtering", () => {
    const scene = projectDesignDocument(documentFixture());
    const index = new CanvasSpatialIndex();
    index.rebuild(scene);
    const selection = new CanvasSelectionModel();
    expect(selection.click({ x: 120, y: 80 }, index)).toBe("text");
    selection.marquee({ x: 100, y: 50, width: 400, height: 300 }, index);
    expect(selection.snapshot().ids).toContain("locked");
    expect(selection.transformableIds(scene)).not.toContain("locked");
  });
});

describe("NODE-40 constraint-aware transform commit", () => {
  it("rolls back visual candidate when a hard lock denies pointer-up commit", () => {
    const controller = new CanvasController(documentFixture());
    const lock: DesignConstraint = {
      id: "lock-shape-position",
      type: "LOCK_POSITION",
      scope: { node_ids: ["shape"] },
      severity: "HARD",
      source: "USER_EXPLICIT",
      priority: 1000,
      parameters: {},
      active: true,
      document_version: 3,
    };
    controller.setConstraints([lock]);
    controller.selection.set(["shape"]);
    const session = controller.beginTransform("test-shape-drag");
    session.previewMove(50, 0);
    expect(session.previewDocument().nodes.shape?.transform?.x).toBe(270);
    const result = controller.commitTransform(session);
    expect(result.accepted).toBe(false);
    expect(result.guarded.preflight.decision).toBe("DENY");
    expect(controller.snapshot().document.nodes.shape?.transform?.x).toBe(220);
  });

  it("commits an unlocked transform through Design IR and increments document version", () => {
    const controller = new CanvasController(documentFixture());
    controller.selection.set(["text"]);
    const session = controller.beginTransform("test-text-drag");
    session.previewMove(15, -5);
    const result = controller.commitTransform(session);
    expect(result.accepted).toBe(true);
    expect(controller.snapshot().document.nodes.text?.transform?.x).toBe(25);
    expect(controller.snapshot().document.nodes.text?.transform?.y).toBe(15);
    expect(controller.snapshot().document.metadata.document_version).toBe(4);
  });
});
