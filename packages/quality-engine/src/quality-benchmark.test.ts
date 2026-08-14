import { describe, expect, it } from "vitest";
import type { DesignDocument } from "../../design-ir/src/index";
import { evaluateDeterministicSignals } from "./deterministic";
import type { CriticSubject } from "./types";

function largeSubject(nodeCount = 2000): CriticSubject {
  const nodes: Record<string, DesignDocument["nodes"][string]> = {
    root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
    frame: { id: "frame", kind: "FRAME", parent_id: "root", children: [], transform: { x: 0, y: 0, width: 1200, height: 1200 } },
  };
  const children: string[] = [];
  for (let i = 0; i < nodeCount; i += 1) {
    const id = `node-${i}`;
    children.push(id);
    nodes[id] = {
      id,
      kind: i % 5 === 0 ? "TEXT" : "SHAPE",
      parent_id: "frame",
      children: [],
      ...(i % 5 === 0 ? { content: `Label ${i}` } : {}),
      transform: { x: i % 61, y: i % 47, width: 20, height: 12 },
      ...(i % 5 === 0 ? { metadata: { measured_width: 19, measured_height: 11, foreground_color: "#111111", background_color: "#ffffff" } } : {}),
    };
  }
  nodes.frame = { ...nodes.frame!, children };
  const design_document: DesignDocument = { schema_version: "1.0", document_id: "benchmark-doc", unit: "px", root_id: "root", nodes, resources: {}, metadata: { document_version: 12 } };
  return {
    organization_id: "org",
    project_id: "project",
    artifact_id: "artifact",
    artifact_version_id: "version",
    design_document_version_id: "design-version",
    design_document,
    rendered_asset_ref: "preview",
    width: 2400,
    height: 2400,
    metadata: { minimum_export_width: 1200, minimum_export_height: 1200 },
  };
}

describe("NODE-50 deterministic critic scale harness", () => {
  it("evaluates a 2k-node document deterministically without model access", () => {
    const subject = largeSubject();
    const first = evaluateDeterministicSignals(subject);
    const second = evaluateDeterministicSignals(subject);
    expect(Object.keys(subject.design_document.nodes)).toHaveLength(2002);
    expect(first).toEqual(second);
    expect(first.some((item) => item.dimension === "CONTRAST")).toBe(true);
    expect(first.some((item) => item.dimension === "RESOLUTION_EXPORT_READINESS")).toBe(true);
    expect(first.flatMap((item) => item.repair_operations ?? [])).toHaveLength(0);
  });
});
