import { describe, expect, it } from "vitest";
import { executeOperations, getDocumentVersion, type DesignDocument } from "@lumi/design-ir";
import { groupOperations, textOperations, transformOperations, ungroupOperations } from "./operations";

function document(): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "doc-inspector",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
      frame: {
        id: "frame",
        kind: "FRAME",
        parent_id: "root",
        children: ["a", "b", "text"],
        transform: { x: 100, y: 100, width: 1000, height: 1000 },
      },
      a: {
        id: "a", kind: "SHAPE", parent_id: "frame", children: [],
        transform: { x: 40, y: 50, width: 100, height: 80 },
      },
      b: {
        id: "b", kind: "SHAPE", parent_id: "frame", children: [],
        transform: { x: 200, y: 100, width: 120, height: 90 },
      },
      text: {
        id: "text", kind: "TEXT", parent_id: "frame", children: [], content: "Hello",
        transform: { x: 20, y: 300, width: 300, height: 80 }, metadata: { font_size: 24 },
      },
    },
    resources: {},
    metadata: { document_version: 7 },
  };
}

describe("Layers / Inspector DesignOperation builders", () => {
  it("groups sibling nodes while preserving their frame-local positions", () => {
    const before = document();
    const group = groupOperations(before, ["a", "b"]);
    expect(group).not.toBeNull();
    const result = executeOperations(before, group!.operations);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(getDocumentVersion(result.document)).toBe(8);
    const created = result.document.nodes[group!.group_id]!;
    expect(created.kind).toBe("GROUP");
    expect(created.transform).toMatchObject({ x: 40, y: 50, width: 280, height: 140 });
    expect(result.document.nodes.a?.parent_id).toBe(group!.group_id);
    expect(result.document.nodes.a?.transform).toMatchObject({ x: 0, y: 0 });
    expect(result.document.nodes.b?.transform).toMatchObject({ x: 160, y: 50 });
  });

  it("ungroups a zero-rotation group and restores child coordinates", () => {
    const first = groupOperations(document(), ["a", "b"])!;
    const grouped = executeOperations(document(), first.operations);
    expect(grouped.ok).toBe(true);
    if (!grouped.ok) return;
    const ungroup = ungroupOperations(grouped.document, first.group_id);
    expect(ungroup).not.toBeNull();
    const ungrouped = executeOperations(grouped.document, ungroup!.operations);
    expect(ungrouped.ok).toBe(true);
    if (!ungrouped.ok) return;
    expect(ungrouped.document.nodes[first.group_id]).toBeUndefined();
    expect(ungrouped.document.nodes.a?.parent_id).toBe("frame");
    expect(ungrouped.document.nodes.a?.transform).toMatchObject({ x: 40, y: 50 });
    expect(ungrouped.document.nodes.b?.transform).toMatchObject({ x: 200, y: 100 });
  });

  it("builds transform and typography edits as versioned semantic operations", () => {
    const source = document();
    const ops = [
      ...transformOperations(source, "a", { x: 88, width: 140, rotation_deg: 15 }),
      ...textOperations(source, "text", { content: "Summer", font_size: 42, text_align: "center", fill: "#222222" }),
    ];
    expect(ops.every((op) => op.expected_document_version === 7)).toBe(true);
    const result = executeOperations(source, ops);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.document.nodes.a?.transform).toMatchObject({ x: 88, width: 140, rotation_deg: 15 });
    expect(result.document.nodes.text?.content).toBe("Summer");
    expect(result.document.nodes.text?.metadata).toMatchObject({ font_size: 42, text_align: "center", fill: "#222222" });
  });
});
