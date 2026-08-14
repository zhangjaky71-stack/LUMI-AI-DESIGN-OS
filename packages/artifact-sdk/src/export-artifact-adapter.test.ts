import { describe, expect, it } from "vitest";
import { ArtifactEngine } from "./engine";
import { ArtifactEngineExportAdapter } from "./export-artifact-adapter";
import { ExportEngine } from "./export-engine";
import type { ExportRendererPort, ExportSourceSnapshot, ExportSpec } from "./export-engine-types";
import { InMemoryExportJobRepository, InMemoryExportObjectStore, RecordingExportEvents, StaticExportSource } from "./export-memory";

const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const HASH_C = "c".repeat(64);
const GIT_SHA = "1".repeat(40);

function seedArtifactEngine(): ArtifactEngine {
  const engine = new ArtifactEngine();
  engine.addArtifact({ id: "artifact-1", organization_id: "org-1", project_id: "project-1", type: "DESIGN_DOCUMENT", title: "Source", archived: false });
  engine.addBranch({ id: "source-branch", organization_id: "org-1", artifact_id: "artifact-1", name: "main", base_version_id: null, head_version_id: null, created_by: "user-1" });
  engine.addVersion({
    id: "artifact-version-0001",
    organization_id: "org-1",
    artifact_id: "artifact-1",
    branch_id: "source-branch",
    parent_version_id: null,
    schema_version: "design.v1",
    version_number: 1,
    status: "READY",
    content_hash: HASH_A,
    constraint_snapshot_hash: HASH_B,
    created_by_type: "USER",
    created_by_id: "user-1",
    created_at: "2026-08-14T00:00:00.000Z",
    design_document_version_id: "design-version-0001",
  }, null);
  return engine;
}

function sourceSnapshot(): ExportSourceSnapshot {
  return {
    organization_id: "org-1",
    project_id: "project-1",
    artifact_id: "artifact-1",
    artifact_version_id: "artifact-version-0001",
    design_document_version_id: "design-version-0001",
    content_hash: HASH_A,
    constraint_snapshot_hash: HASH_B,
    compiler_provenance: {
      compiler_version: "1.0.0",
      document_id: "doc-1",
      schema_version: "1.0.0",
      document_version: 1,
      resource_versions: {},
      font_versions: {},
      compile_hash: HASH_C,
    },
    design_document: { document_id: "doc-1", nodes: {} },
    render_plan: { compiler_version: "1.0.0", document_id: "doc-1", items: [] },
    rights_summary: { commercial_use: "ALLOWED" },
    model_refs: [],
    source_provenance_refs: [],
  };
}

function exportSpec(): ExportSpec {
  return {
    organization_id: "org-1",
    project_id: "project-1",
    requested_by: "user-1",
    operation_id: "export-op-1",
    artifact_version_id: "artifact-version-0001",
    design_document_version_id: "design-version-0001",
    variants: [{ variant_id: "png", frame_ids: ["frame-1"], format: "PNG", filename: "final" }],
    filename_template: "final",
    include_manifest: true,
    retention_seconds: 3600,
  };
}

describe("NODE-49 Artifact integration", () => {
  it("creates READY export ArtifactVersion with verified file, provenance and EXPORTED_FROM lineage", async () => {
    const artifactEngine = seedArtifactEngine();
    const source = new StaticExportSource();
    source.add(sourceSnapshot());
    const jobs = new InMemoryExportJobRepository();
    const store = new InMemoryExportObjectStore();
    const renderer: ExportRendererPort = {
      async render() {
        return { bytes: new Uint8Array([0x89, 0x50, 0x4e, 0x47, 1, 2, 3]), mime_type: "image/png", width: 100, height: 80 };
      },
    };
    const artifacts = new ArtifactEngineExportAdapter({ engine: artifactEngine, store, code_git_sha: GIT_SHA });
    const exportEngine = new ExportEngine({
      source,
      jobs,
      renderer,
      store,
      artifacts,
      events: new RecordingExportEvents(),
      now: () => "2026-08-14T00:00:00.000Z",
    });
    const created = await exportEngine.start(exportSpec());
    const ready = await exportEngine.execute("org-1", created.export_job_id);
    expect(ready.status).toBe("READY");
    const outputVersions = [...artifactEngine.versions.values()].filter((version) => version.id !== "artifact-version-0001");
    expect(outputVersions).toHaveLength(2);
    expect(outputVersions.every((version) => version.status === "READY")).toBe(true);
    expect([...artifactEngine.edges.values()].filter((edge) => edge.type === "EXPORTED_FROM")).toHaveLength(2);
    expect([...artifactEngine.edges.values()].every((edge) => edge.from_version_id === "artifact-version-0001")).toBe(true);
    expect([...artifactEngine.provenance.values()].every((record) => record.compiler?.compile_hash === HASH_C)).toBe(true);
    expect([...artifactEngine.files.values()].some((file) => file.mime_type === "image/png" && file.width === 100 && file.height === 80)).toBe(true);
  });

  it("rejects source Artifact history drift before attaching output", async () => {
    const artifactEngine = seedArtifactEngine();
    const source = new StaticExportSource();
    source.add(sourceSnapshot());
    const jobs = new InMemoryExportJobRepository();
    const store = new InMemoryExportObjectStore();
    const renderer: ExportRendererPort = { async render() { return { bytes: new Uint8Array([1]), mime_type: "image/png", width: 1, height: 1 }; } };
    const artifacts = new ArtifactEngineExportAdapter({ engine: artifactEngine, store, code_git_sha: GIT_SHA });
    artifactEngine.versions.set("artifact-version-0001", { ...artifactEngine.versions.get("artifact-version-0001")!, content_hash: "d".repeat(64) });
    const exportEngine = new ExportEngine({ source, jobs, renderer, store, artifacts, events: new RecordingExportEvents(), now: () => "2026-08-14T00:00:00.000Z" });
    const created = await exportEngine.start(exportSpec());
    const failed = await exportEngine.execute("org-1", created.export_job_id);
    expect(failed.status).toBe("FAILED");
    expect(failed.error_code).toBe("EXPORT_SOURCE_ARTIFACT_SNAPSHOT_MISMATCH");
  });
});
