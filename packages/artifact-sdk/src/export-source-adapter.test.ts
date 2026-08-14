import { describe, expect, it } from "vitest";
import { CanvasCompiler } from "../../canvas-sdk/src/compiler";
import type { DesignDocument } from "../../design-ir/src/index";
import { ArtifactEngine } from "./engine";
import type { ExportSpec } from "./export-engine-types";
import { ArtifactEngineExportSource } from "./export-source-adapter";

const CONTENT = "a".repeat(64);
const CONSTRAINT = "b".repeat(64);

function document(): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "export-source-doc",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
      frame: { id: "frame", kind: "FRAME", parent_id: "root", children: ["title", "image"], transform: { x: 0, y: 0, width: 600, height: 400 } },
      title: { id: "title", kind: "TEXT", parent_id: "frame", children: [], content: "Export", transform: { x: 20, y: 20, width: 200, height: 40 }, metadata: { font_asset_id: "font-inter" } },
      image: { id: "image", kind: "IMAGE", parent_id: "frame", children: [], asset_id: "asset-product", transform: { x: 40, y: 100, width: 300, height: 200 } },
    },
    resources: {
      "font-inter": { family: "Inter", version: "font-v4", uri: "https://signed.example/font?token=secret", weight: 500 },
      "asset-product": { version: "asset-v7", preview_uri: "https://signed.example/asset?token=secret", mime_type: "image/png", width: 1600, height: 1200 },
    },
    metadata: { document_version: 9 },
  };
}

function artifactEngine(): ArtifactEngine {
  const engine = new ArtifactEngine();
  engine.addArtifact({ id: "artifact-source", organization_id: "org-1", project_id: "project-1", type: "DESIGN_DOCUMENT", title: "Source", archived: false });
  engine.addBranch({ id: "source-main", organization_id: "org-1", artifact_id: "artifact-source", name: "main", base_version_id: null, head_version_id: null, created_by: "user-1" });
  engine.addVersion({
    id: "artifact-version-source",
    organization_id: "org-1",
    artifact_id: "artifact-source",
    branch_id: "source-main",
    parent_version_id: null,
    schema_version: "design.v1",
    version_number: 1,
    status: "READY",
    content_hash: CONTENT,
    constraint_snapshot_hash: CONSTRAINT,
    created_by_type: "USER",
    created_by_id: "user-1",
    created_at: "2026-08-14T00:00:00.000Z",
    design_document_version_id: "design-v9",
  }, null);
  return engine;
}

function exportSpec(): ExportSpec {
  return {
    organization_id: "org-1",
    project_id: "project-1",
    requested_by: "user-1",
    operation_id: "op-source",
    artifact_version_id: "artifact-version-source",
    design_document_version_id: "design-v9",
    variants: [{ variant_id: "png", frame_ids: ["frame"], format: "PNG" }],
    filename_template: "export",
    include_manifest: true,
    retention_seconds: 3600,
  };
}

describe("NODE-49 exact source resolver", () => {
  it("compiles the exact DesignVersion and strips signed resource URIs from durable snapshot", async () => {
    const exact = document();
    const resolver = new ArtifactEngineExportSource({
      artifacts: artifactEngine(),
      designs: { async loadExact(args) { expect(args.design_document_version_id).toBe("design-v9"); return exact; } },
      compiler: new CanvasCompiler(),
      metadata: {
        async rightsSummary() { return { commercial_use: "ALLOWED" }; },
        async modelRefs() { return ["model:source"]; },
        async provenanceRefs() { return ["provenance:source"]; },
      },
    });
    const snapshot = await resolver.resolveExactSnapshot(exportSpec());
    expect(snapshot.content_hash).toBe(CONTENT);
    expect(snapshot.compiler_provenance.document_version).toBe(9);
    expect(snapshot.compiler_provenance.resource_versions).toEqual({ "asset-product": "asset-v7" });
    expect(snapshot.compiler_provenance.font_versions).toEqual({ "font-inter": "font-v4" });
    expect(snapshot.compiler_provenance.compile_hash).toMatch(/^[0-9a-f]{64}$/);
    const durable = JSON.stringify({ design_document: snapshot.design_document, render_plan: snapshot.render_plan });
    expect(durable).not.toContain("signed.example");
    expect(durable).not.toContain("preview_uri");
    expect(durable).not.toMatch(/\"uri\"\s*:/);
    expect(durable).toContain("asset-v7");
    expect(JSON.stringify(exact)).toContain("signed.example");
  });

  it("rejects an ArtifactVersion that does not pin the requested DesignVersion", async () => {
    const resolver = new ArtifactEngineExportSource({
      artifacts: artifactEngine(),
      designs: { async loadExact() { return document(); } },
      compiler: new CanvasCompiler(),
      metadata: { async rightsSummary() { return {}; }, async modelRefs() { return []; }, async provenanceRefs() { return []; } },
    });
    await expect(resolver.resolveExactSnapshot({ ...exportSpec(), design_document_version_id: "design-v10" })).rejects.toThrow("EXPORT_SOURCE_DESIGN_VERSION_NOT_EXACT");
  });
});
