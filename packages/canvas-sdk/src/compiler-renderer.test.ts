import { describe, expect, it, vi } from "vitest";

import type { DesignDocument } from "../../design-ir/src/index";
import { CanvasCompiler } from "./compiler";
import {
  PixiV8RendererAdapter,
  type PixiDisplayHandle,
  type PixiV8Bindings,
} from "./renderer";

function fixture(): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "compiler-renderer",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
      frame: {
        id: "frame",
        kind: "FRAME",
        parent_id: "root",
        children: ["mask", "shape", "title"],
        transform: { width: 500, height: 300 },
      },
      mask: {
        id: "mask",
        kind: "MASK",
        parent_id: "frame",
        children: [],
        transform: { x: 10, y: 10, width: 220, height: 160 },
      },
      shape: {
        id: "shape",
        kind: "SHAPE",
        parent_id: "frame",
        children: [],
        transform: { x: 20, y: 20, width: 180, height: 120 },
        style_refs: ["shape-style"],
        metadata: { mask_id: "mask" },
      },
      title: {
        id: "title",
        kind: "TEXT",
        parent_id: "frame",
        children: [],
        content: "Compiled style",
        transform: { x: 24, y: 210, width: 200, height: 36 },
        style_refs: ["text-style"],
      },
    },
    resources: {
      "shape-style": { style: { fill: "#ffcc00" }, version: "s1" },
      "text-style": { style: { fill: "#111111", font_size: 24 }, version: "t1" },
    },
    metadata: { document_version: 1 },
  };
}

function bindingsFixture() {
  const handles = new Map<string, PixiDisplayHandle>();
  const create = (id: string): PixiDisplayHandle => {
    const handle = { id };
    handles.set(id, handle);
    return handle;
  };
  const bindings: PixiV8Bindings = {
    stage: create("stage"),
    createContainer: create,
    createText: (id) => create(id),
    createImage: (id) => create(id),
    createShape: (id) => create(id),
    createVideoPoster: (id) => create(id),
    createPlaceholder: (id) => create(id),
    setLocalMatrix: vi.fn(),
    setCamera: vi.fn(),
    redrawShape: vi.fn(),
    setDisplaySize: vi.fn(),
    setVisible: vi.fn(),
    setText: vi.fn(),
    setAsset: vi.fn(),
    setMask: vi.fn(),
    addChild: vi.fn(),
    removeChild: vi.fn(),
    destroyDisplay: vi.fn(),
    resize: vi.fn(),
    destroy: vi.fn(),
  };
  return { bindings, handles };
}

describe("NODE-41 compiler to Pixi bridge", () => {
  it("materializes resolved styles and mask dependencies through renderer-neutral bindings", () => {
    const compiled = new CanvasCompiler().compileStructure(fixture());
    expect(compiled.ok).toBe(true);
    if (!compiled.ok) return;
    expect(compiled.snapshot.nodes.get("shape")?.resolved_style.fill).toBe("#ffcc00");
    expect(compiled.snapshot.nodes.get("title")?.resolved_style.font_size).toBe(24);

    const { bindings, handles } = bindingsFixture();
    const renderer = new PixiV8RendererAdapter(bindings);
    renderer.sync(compiled.snapshot, new Set(compiled.snapshot.paint_order));

    expect(bindings.redrawShape).toHaveBeenCalledWith(
      handles.get("shape"),
      expect.objectContaining({
        id: "shape",
        resolved_style: expect.objectContaining({ fill: "#ffcc00" }),
      }),
    );
    expect(bindings.setText).toHaveBeenCalledWith(
      handles.get("title"),
      "Compiled style",
      expect.objectContaining({
        resolved_style: expect.objectContaining({ font_size: 24 }),
      }),
    );
    expect(bindings.setMask).toHaveBeenCalledWith(handles.get("shape"), handles.get("mask"));
  });
});
