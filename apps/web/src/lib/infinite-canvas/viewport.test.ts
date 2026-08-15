import { describe, expect, it } from "vitest";
import { projectDesignDocument } from "@lumi/canvas-sdk";
import type { DesignDocument, DesignNode } from "@lumi/design-ir";
import { cullSceneNodes } from "./viewport";

function largeDocument(count: number): DesignDocument {
  const children: string[] = [];
  const nodes: Record<string, DesignNode> = {
    root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children },
  };
  for (let index = 0; index < count; index += 1) {
    const id = `shape-${index}`;
    children.push(id);
    nodes[id] = {
      id,
      kind: "SHAPE",
      parent_id: "root",
      children: [],
      transform: {
        x: (index % 50) * 160,
        y: Math.floor(index / 50) * 160,
        width: 120,
        height: 120,
      },
    };
  }
  return {
    schema_version: "1.0",
    document_id: "large-doc",
    unit: "px",
    root_id: "root",
    nodes,
    resources: {},
    metadata: { document_version: 1 },
  };
}

describe("Infinite Canvas viewport culling", () => {
  it("keeps a 2k-node scene bounded to the visible viewport", () => {
    const scene = projectDesignDocument(largeDocument(2_000));
    const all = scene.paint_order.flatMap((id) => {
      const node = scene.nodes.get(id);
      return node ? [node] : [];
    });
    const visible = cullSceneNodes(
      all,
      { x: 0, y: 0, zoom: 1 },
      { width: 1200, height: 800 },
      new Set(),
    );
    expect(all.length).toBe(2_001);
    expect(visible.length).toBeGreaterThan(0);
    expect(visible.length).toBeLessThan(150);
  });

  it("keeps selected offscreen nodes renderable for transform feedback", () => {
    const scene = projectDesignDocument(largeDocument(50));
    const far = scene.nodes.get("shape-49")!;
    const visible = cullSceneNodes(
      [far],
      { x: 0, y: 0, zoom: 1 },
      { width: 200, height: 200 },
      new Set([far.id]),
    );
    expect(visible.map((node) => node.id)).toEqual([far.id]);
  });
});
