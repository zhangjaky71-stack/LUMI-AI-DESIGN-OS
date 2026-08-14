import { describe, expect, it } from "vitest";
import { ExportEngine } from "./export-engine";
import type { ExportRendererPort, ExportSourceSnapshot, ExportSpec } from "./export-engine-types";
import { InMemoryExportJobRepository, InMemoryExportObjectStore, RecordingExportArtifacts, RecordingExportEvents, StaticExportSource } from "./export-memory";
import { readStoreZipEntries, writeStoreZip } from "./export-zip";

const HASH = "a".repeat(64);

function source(): ExportSourceSnapshot {
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
      resource_versions: { asset: "v1" },
      font_versions: {},
      compile_hash: "c".repeat(64),
    },
    design_document: { document_id: "doc-1", nodes: {}, resources: { asset: { version: "v1" } } },
    render_plan: { compiler_version: "1.0.0", document_id: "doc-1", items: [] },
    rights_summary: { commercial_use: "ALLOWED", source: "OWNED" },
    model_refs: ["model:one"],
    source_provenance_refs: ["provenance:one"],
    project_snapshot: { name: "Campaign" },
  };
}

function spec(): ExportSpec {
  return {
    organization_id: "org-1",
    project_id: "project-1",
    requested_by: "user-1",
    operation_id: "op-package",
    artifact_version_id: "artifact-version-1",
    design_document_version_id: "design-version-1",
    variants: [
      { variant_id: "svg", frame_ids: ["frame-1"], format: "SVG", filename: "design" },
      { variant_id: "lumi", frame_ids: [], format: "LUMI_PACKAGE", filename: "project" },
    ],
    filename_template: "export",
    include_manifest: true,
    retention_seconds: 3600,
  };
}

describe("NODE-49 LUMI package", () => {
  it("contains exact durable project/design/provenance metadata and no runtime URL", async () => {
    const sources = new StaticExportSource();
    sources.add(source());
    const jobs = new InMemoryExportJobRepository();
    const store = new InMemoryExportObjectStore();
    const renderer: ExportRendererPort = {
      async render() { return { bytes: new TextEncoder().encode("<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>"), mime_type: "image/svg+xml", width: 100, height: 100 }; },
    };
    const engine = new ExportEngine({ source: sources, jobs, renderer, store, artifacts: new RecordingExportArtifacts(), events: new RecordingExportEvents(), now: () => "2026-08-14T00:00:00.000Z" });
    const ready = await engine.execute("org-1", (await engine.start(spec())).export_job_id);
    expect(ready.status).toBe("READY");
    const packageFile = ready.files.find((file) => file.variant_id === "lumi")!;
    const entries = readStoreZipEntries(await store.get(packageFile.storage_key));
    expect([...entries.keys()]).toEqual(expect.arrayContaining([
      "lumi/manifest.json",
      "lumi/design-document.json",
      "lumi/compiler-provenance.json",
      "lumi/rights-summary.json",
      "lumi/project-snapshot.json",
      "lumi/exports/design.svg",
    ]));
    const decoded = [...entries.values()].map((bytes) => new TextDecoder().decode(bytes)).join("\n");
    expect(decoded).not.toMatch(/https?:\/\//);
    expect(decoded).not.toContain("api_key");
    expect(decoded).toContain("artifact-version-1");
    expect(decoded).toContain("design-version-1");
    expect(decoded).toContain("model:one");
  });

  it("detects ZIP payload tampering through CRC validation", () => {
    const zip = writeStoreZip([{ name: "safe/file.txt", bytes: new TextEncoder().encode("hello") }]);
    const tampered = Uint8Array.from(zip);
    const marker = new TextEncoder().encode("hello");
    const index = tampered.findIndex((value, offset) => marker.every((item, i) => tampered[offset + i] === item));
    expect(index).toBeGreaterThan(0);
    tampered[index] ^= 0xff;
    expect(() => readStoreZipEntries(tampered)).toThrow("EXPORT_ZIP_CRC_MISMATCH");
  });
});
