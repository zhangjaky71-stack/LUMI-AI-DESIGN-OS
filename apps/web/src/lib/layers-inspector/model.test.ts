import { describe, expect, it } from "vitest";
import { CanvasController } from "@lumi/canvas-sdk";
import type { DesignDocument } from "@lumi/design-ir";
import { buildCanvasEditorState } from "./model";

function fixture(): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "doc-layers",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
      frame: {
        id: "frame", kind: "FRAME", name: "Frame", parent_id: "root", children: ["group", "top"],
        visible: false, transform: { x: 0, y: 0, width: 500, height: 500 },
      },
      group: {
        id: "group", kind: "GROUP", name: "Group", parent_id: "frame", children: ["child"],
        locked: true, transform: { x: 10, y: 20, width: 200, height: 200 },
      },
      child: {
        id: "child", kind: "TEXT", name: "Child", parent_id: "group", children: [], content: "Copy",
        transform: { x: 5, y: 8, width: 80, height: 20 }, metadata: { fill: "#111111", font_size: 18 },
      },
      top: {
        id: "top", kind: "SHAPE", name: "Top", parent_id: "frame", children: [],
        transform: { x: 250, y: 250, width: 80, height: 80 },
      },
    },
    resources: {},
    metadata: { document_version: 4 },
  };
}

describe("Layers / Inspector model", () => {
  it("projects topmost layers first and keeps local vs effective visibility/lock", () => {
    const controller = new CanvasController(fixture());
    controller.selection.set(["child"], "child");
    const state = buildCanvasEditorState(controller.snapshot(), 4, "SAVED");
    expect(state.layers.map((layer) => layer.id)).toEqual(["frame"]);
    expect(state.layers[0]?.children.map((layer) => layer.id)).toEqual(["top", "group"]);
    const group = state.layers[0]?.children[1];
    const child = group?.children[0];
    expect(child?.visible).toBe(true);
    expect(child?.effective_visible).toBe(false);
    expect(child?.locked).toBe(false);
    expect(child?.effective_locked).toBe(true);
    expect(child?.selected).toBe(true);
  });

  it("marks one zero-rotation group as ungroupable and sibling selections as groupable", () => {
    const controller = new CanvasController(fixture());
    controller.selection.set(["group"], "group");
    expect(buildCanvasEditorState(controller.snapshot(), 4, "SAVED").can_ungroup).toBe(false);
    controller.selection.set(["group", "top"], "top");
    expect(buildCanvasEditorState(controller.snapshot(), 4, "SAVED").can_group).toBe(false);

    const unlocked: DesignDocument = {
      ...fixture(),
      nodes: {
        ...fixture().nodes,
        group: { ...fixture().nodes.group!, locked: false },
      },
    };
    const second = new CanvasController(unlocked);
    second.selection.set(["group", "top"], "top");
    expect(buildCanvasEditorState(second.snapshot(), 4, "SAVED").can_group).toBe(true);
    second.selection.set(["group"], "group");
    expect(buildCanvasEditorState(second.snapshot(), 4, "SAVED").can_ungroup).toBe(true);
  });
});
