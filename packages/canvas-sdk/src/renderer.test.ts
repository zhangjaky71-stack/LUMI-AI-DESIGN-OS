import { describe, expect, it, vi } from "vitest";

import type { DesignDocument } from "../../design-ir/src/index";
import { projectDesignDocument } from "./ir-scene";
import {
  PixiV8RendererAdapter,
  type PixiDisplayHandle,
  type PixiV8Bindings,
} from "./renderer";

function documentFixture(content = "Hello", frameWidth = 300): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "render-doc",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
      frame: {
        id: "frame",
        kind: "FRAME",
        parent_id: "root",
        children: ["text"],
        transform: { x: 10, y: 10, width: frameWidth, height: 200 },
      },
      text: {
        id: "text",
        kind: "TEXT",
        parent_id: "frame",
        children: [],
        content,
        transform: { x: 20, y: 30, width: 140, height: 30 },
      },
    },
    resources: {},
    metadata: { document_version: 1 },
  };
}

function fakeBindings() {
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

describe("PixiV8RendererAdapter", () => {
  it("creates renderer objects without contaminating persisted Design IR", () => {
    const document = documentFixture();
    const scene = projectDesignDocument(document);
    const { bindings } = fakeBindings();
    const adapter = new PixiV8RendererAdapter(bindings);
    adapter.setCamera({ x: 20, y: 30, zoom: 2 });
    expect(bindings.setCamera).toHaveBeenCalledWith({ x: 20, y: 30, zoom: 2 });
    const first = adapter.sync(scene, new Set(["frame", "text"]));
    expect(first.created).toBe(3);
    expect(first.updated).toBe(3);
    expect(bindings.redrawShape).toHaveBeenCalled();
    expect(JSON.stringify(document)).not.toContain("stage");
    expect(JSON.stringify(document)).not.toContain("pixi");

    const second = adapter.sync(scene, new Set(["frame", "text"]));
    expect(second.created).toBe(0);
    expect(second.updated).toBe(0);
  });

  it("updates dirty text and resized frame geometry only", () => {
    const { bindings } = fakeBindings();
    const adapter = new PixiV8RendererAdapter(bindings);
    adapter.sync(projectDesignDocument(documentFixture("Before", 300)), new Set(["frame", "text"]));
    const dirty = adapter.sync(
      projectDesignDocument(documentFixture("After", 360)),
      new Set(["frame", "text"]),
    );
    expect(dirty.updated).toBe(2);
    expect(bindings.setText).toHaveBeenCalledWith(
      expect.anything(),
      "After",
      expect.objectContaining({ id: "text" }),
    );
    expect(bindings.redrawShape).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ id: "frame", local_bounds: expect.objectContaining({ width: 360 }) }),
    );
  });

  it("destroys removed objects without recursive double-disposal", () => {
    const { bindings } = fakeBindings();
    const adapter = new PixiV8RendererAdapter(bindings);
    adapter.sync(projectDesignDocument(documentFixture("After")), new Set(["frame", "text"]));
    const withoutText = documentFixture("After");
    const frame = withoutText.nodes.frame!;
    const next: DesignDocument = {
      ...withoutText,
      nodes: {
        root: withoutText.nodes.root!,
        frame: { ...frame, children: [] },
      },
    };
    const removed = adapter.sync(projectDesignDocument(next), new Set(["frame"]));
    expect(removed.removed).toBe(1);
    expect(bindings.destroyDisplay).toHaveBeenCalledTimes(1);
  });
});
