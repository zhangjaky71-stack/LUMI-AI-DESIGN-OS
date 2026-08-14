import { describe, expect, it } from "vitest";
import type { ExportSourceSnapshot } from "./export-engine-types";
import { SafeSvgRenderPlanSerializer } from "./export-svg";

const HASH = "a".repeat(64);

function source(items: readonly Record<string, unknown>[]): ExportSourceSnapshot {
  return {
    organization_id: "org-1",
    project_id: "project-1",
    artifact_id: "artifact-1",
    artifact_version_id: "artifact-version-1",
    design_document_version_id: "design-version-1",
    content_hash: HASH,
    constraint_snapshot_hash: "b".repeat(64),
    compiler_provenance: {
      compiler_version: "1.0.0",
      document_id: "doc-1",
      schema_version: "1.0",
      document_version: 1,
      resource_versions: {},
      font_versions: {},
      compile_hash: "c".repeat(64),
    },
    design_document: { document_id: "doc-1", nodes: { frame: { id: "frame", kind: "FRAME", metadata: {} }, text: { id: "text", kind: "TEXT", metadata: {} } } },
    render_plan: { compiler_version: "1.0.0", document_id: "doc-1", items },
    rights_summary: {},
    model_refs: [],
    source_provenance_refs: [],
  };
}

const matrix = { a: 1, b: 0, c: 0, d: 1, tx: 0, ty: 0 };
const bounds = { x: 0, y: 0, width: 200, height: 100 };
const frame = {
  id: "frame", kind: "FRAME", parent_id: null, visible: true, z_order: 0,
  world_matrix: matrix, local_bounds: bounds, world_bounds: bounds,
  resolved_style: { fill: "#ffffff", opacity: 1, blend_mode: "normal" }, placeholder: false,
};

function serializer() {
  return new SafeSvgRenderPlanSerializer({ async imageDataUri() { return "data:image/png;base64,iVBORw0KGgo="; } });
}

describe("NODE-49 SVG fidelity boundaries", () => {
  it("preserves explicit multiline text line height and center alignment", async () => {
    const text = {
      id: "text", kind: "TEXT", parent_id: "frame", visible: true, z_order: 1,
      world_matrix: { ...matrix, tx: 10, ty: 20 }, local_bounds: { x: 0, y: 0, width: 100, height: 48 }, world_bounds: { x: 10, y: 20, width: 100, height: 48 },
      resolved_style: { fill: "#111111", opacity: 1, blend_mode: "normal", font_size: 20, line_height: 24, align: "center" },
      resolved_text: { content: "First\nSecond", metrics: { width: 72, height: 48, baseline: 16 } }, placeholder: false,
    };
    const [page] = await serializer().renderPages(source([frame, text]), { variant_id: "svg", frame_ids: ["frame"], format: "SVG" });
    expect(page!.svg).toContain('text-anchor="middle"');
    expect(page!.svg).toContain('<tspan x="50" dy="20">First</tspan>');
    expect(page!.svg).toContain('<tspan x="50" dy="24">Second</tspan>');
  });

  it("rejects text when compiler metrics cannot be represented by V1 text layout", async () => {
    const text = {
      id: "text", kind: "TEXT", parent_id: "frame", visible: true, z_order: 1,
      world_matrix: matrix, local_bounds: bounds, world_bounds: bounds,
      resolved_style: { fill: "#111111", blend_mode: "normal", font_size: 20, line_height: 24 },
      resolved_text: { content: "single line", metrics: { width: 120, height: 48, baseline: 16 } }, placeholder: false,
    };
    await expect(serializer().renderPages(source([frame, text]), { variant_id: "svg", frame_ids: ["frame"], format: "SVG" })).rejects.toThrow("EXPORT_TEXT_METRICS_LAYOUT_UNSUPPORTED_V1");
  });

  it("rejects mask or clip links instead of silently dropping them", async () => {
    const clipped = { ...frame, id: "shape", kind: "SHAPE", parent_id: "frame", z_order: 1, clip_id: "clip-1" };
    await expect(serializer().renderPages(source([frame, clipped]), { variant_id: "svg", frame_ids: ["frame"], format: "SVG" })).rejects.toThrow("EXPORT_SVG_MASK_CLIP_NOT_IMPLEMENTED_V1");
  });

  it("rejects non-normal blend mode instead of approximating Pixi semantics", async () => {
    const blended = { ...frame, id: "shape", kind: "SHAPE", parent_id: "frame", z_order: 1, resolved_style: { fill: "#111", blend_mode: "multiply" } };
    await expect(serializer().renderPages(source([frame, blended]), { variant_id: "svg", frame_ids: ["frame"], format: "SVG" })).rejects.toThrow("EXPORT_SVG_BLEND_MODE_NOT_IMPLEMENTED_V1");
  });
});
