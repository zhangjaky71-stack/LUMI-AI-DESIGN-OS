import { describe, expect, it } from "vitest";
import { ExportDownloadService, ExportEngine } from "./export-engine";
import type { ExportRendererPort, ExportSourceSnapshot, ExportSpec, RenderedExportPayload } from "./export-engine-types";
import {
  InMemoryExportJobRepository,
  InMemoryExportObjectStore,
  RecordingExportArtifacts,
  RecordingExportEvents,
  RecordingExportSigner,
  StaticExportAuthorization,
  StaticExportSource,
} from "./export-memory";
import { inspectRasterPdf, writeRasterPdf } from "./export-pdf";
import { CompositeExportRenderer, type ExportRasterCodecPort } from "./export-renderer";
import { assertExportFormat, assertExportProfile, safeZipEntryName, sanitizeExportFilename } from "./export-security";
import { SafeSvgRenderPlanSerializer } from "./export-svg";
import { WorkerBackedRasterCodec } from "./export-worker-protocol";
import { inspectZipEntries, writeStoreZip } from "./export-zip";

const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const HASH_C = "c".repeat(64);

function snapshot(overrides: Partial<ExportSourceSnapshot> = {}): ExportSourceSnapshot {
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
    model_refs: ["model:fixture-v1"],
    source_provenance_refs: ["provenance:1"],
    ...overrides,
  };
}

function spec(overrides: Partial<ExportSpec> = {}): ExportSpec {
  return {
    organization_id: "org-1",
    project_id: "project-1",
    requested_by: "user-1",
    operation_id: "operation-1",
    artifact_version_id: "artifact-version-0001",
    design_document_version_id: "design-version-0001",
    variants: [
      { variant_id: "svg-main", frame_ids: ["frame-1"], format: "SVG", filename: "设计稿" },
      { variant_id: "batch", frame_ids: [], format: "ZIP", filename: "交付包" },
    ],
    filename_template: "export",
    include_manifest: true,
    retention_seconds: 3600,
    ...overrides,
  };
}

class RecordingRenderer implements ExportRendererPort {
  count = 0;
  readonly hashes: string[] = [];
  async render(source: ExportSourceSnapshot): Promise<RenderedExportPayload> {
    this.count += 1;
    this.hashes.push(source.content_hash);
    return { bytes: new TextEncoder().encode("<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>"), mime_type: "image/svg+xml", width: 100, height: 100 };
  }
}

function harness(sourceSnapshot = snapshot()) {
  const source = new StaticExportSource();
  source.add(sourceSnapshot);
  const jobs = new InMemoryExportJobRepository();
  const renderer = new RecordingRenderer();
  const store = new InMemoryExportObjectStore();
  const artifacts = new RecordingExportArtifacts();
  const events = new RecordingExportEvents();
  const engine = new ExportEngine({ source, jobs, renderer, store, artifacts, events, now: () => "2026-08-14T00:00:00.000Z" });
  return { source, jobs, renderer, store, artifacts, events, engine };
}

function renderableSource(): ExportSourceSnapshot {
  return snapshot({
    design_document: {
      document_id: "doc-1",
      nodes: {
        "frame-1": { id: "frame-1", kind: "FRAME", metadata: {} },
        "path-1": { id: "path-1", kind: "VECTOR_PATH", metadata: { svg_path: "M0 0 L20 0 L20 20 Z" } },
        "text-1": { id: "text-1", kind: "TEXT", metadata: {} },
        "image-1": { id: "image-1", kind: "IMAGE", metadata: {} },
      },
    },
    render_plan: {
      compiler_version: "1.0.0",
      document_id: "doc-1",
      items: [
        { id: "frame-1", kind: "FRAME", parent_id: null, z_order: 0, visible: true, world_matrix: { a: 1, b: 0, c: 0, d: 1, tx: 0, ty: 0 }, local_bounds: { x: 0, y: 0, width: 100, height: 100 }, world_bounds: { x: 0, y: 0, width: 100, height: 100 }, resolved_style: { fill: "#ffffff" }, placeholder: false },
        { id: "path-1", kind: "VECTOR_PATH", parent_id: "frame-1", z_order: 1, visible: true, world_matrix: { a: 1, b: 0, c: 0, d: 1, tx: 10, ty: 10 }, local_bounds: { x: 0, y: 0, width: 20, height: 20 }, world_bounds: { x: 10, y: 10, width: 20, height: 20 }, resolved_style: { fill: "#111111" }, placeholder: false },
        { id: "text-1", kind: "TEXT", parent_id: "frame-1", z_order: 2, visible: true, world_matrix: { a: 1, b: 0, c: 0, d: 1, tx: 10, ty: 40 }, local_bounds: { x: 0, y: 0, width: 60, height: 20 }, world_bounds: { x: 10, y: 40, width: 60, height: 20 }, resolved_style: { fill: "#111111", font_size: 14 }, resolved_text: { content: "Hello" }, placeholder: false },
        { id: "image-1", kind: "IMAGE", parent_id: "frame-1", z_order: 3, visible: true, world_matrix: { a: 1, b: 0, c: 0, d: 1, tx: 70, ty: 70 }, local_bounds: { x: 0, y: 0, width: 20, height: 20 }, world_bounds: { x: 70, y: 70, width: 20, height: 20 }, resolved_style: {}, resolved_resource: { asset_id: "asset-1", version: "v1", status: "READY", mime_type: "image/png" }, placeholder: false },
      ],
    },
  });
}

function serializer(): SafeSvgRenderPlanSerializer {
  return new SafeSvgRenderPlanSerializer({ async imageDataUri() { return "data:image/png;base64,iVBORw0KGgo="; } });
}

describe("NODE-49 exact Export Engine", () => {
  it("pins the exact ArtifactVersion and DesignVersion before worker execution", async () => {
    const h = harness();
    const created = await h.engine.start(spec());
    expect(created.source.content_hash).toBe(HASH_A);
    h.source.add(snapshot({ content_hash: "d".repeat(64) }));
    const ready = await h.engine.execute(created.organization_id, created.export_job_id);
    expect(ready.status).toBe("READY");
    expect(h.renderer.hashes).toEqual([HASH_A]);
    expect(h.source.resolve_count).toBe(1);
  });

  it("reuses a READY semantic fingerprint during retention without rerender", async () => {
    const h = harness();
    const created = await h.engine.start(spec());
    const ready = await h.engine.execute(created.organization_id, created.export_job_id);
    const reused = await h.engine.start(spec({ operation_id: "operation-2" }));
    expect(reused.export_job_id).toBe(ready.export_job_id);
    expect(h.renderer.count).toBe(1);
  });

  it("builds safe batch ZIP, deterministic manifest and unicode filenames", async () => {
    const h = harness();
    const ready = await h.engine.execute("org-1", (await h.engine.start(spec())).export_job_id);
    expect(ready.status).toBe("READY");
    expect(ready.manifest?.artifact_version_id).toBe("artifact-version-0001");
    expect(ready.manifest?.compiler.compile_hash).toBe(HASH_C);
    expect(ready.manifest?.manifest_sha256).toMatch(/^[0-9a-f]{64}$/);
    const zip = ready.files.find((file) => file.mime_type === "application/zip")!;
    expect(inspectZipEntries(await h.store.get(zip.storage_key))).toEqual(expect.arrayContaining(["files/设计稿.svg", "manifest.json"]));
  });

  it("authorizes each re-download and only re-signs the existing object", async () => {
    const h = harness();
    const ready = await h.engine.execute("org-1", (await h.engine.start(spec())).export_job_id);
    const file = ready.files[0]!;
    const signer = new RecordingExportSigner();
    const denied = new ExportDownloadService({ jobs: h.jobs, authorization: new StaticExportAuthorization(false), signer, now: () => "2026-08-14T00:10:00.000Z" });
    await expect(denied.download({ organization_id: "org-1", actor_id: "u", export_job_id: ready.export_job_id, file_id: file.file_id })).rejects.toThrow("EXPORT_DOWNLOAD_FORBIDDEN");
    const allowed = new ExportDownloadService({ jobs: h.jobs, authorization: new StaticExportAuthorization(true), signer, now: () => "2026-08-14T00:10:00.000Z" });
    await allowed.download({ organization_id: "org-1", actor_id: "u", export_job_id: ready.export_job_id, file_id: file.file_id, expires_seconds: 120 });
    await allowed.download({ organization_id: "org-1", actor_id: "u", export_job_id: ready.export_job_id, file_id: file.file_id, expires_seconds: 120 });
    expect(signer.calls).toHaveLength(2);
    expect(h.renderer.count).toBe(1);
  });

  it("rejects floating versions, false color claims, PSD and hidden metadata", async () => {
    const h = harness();
    await expect(h.engine.start(spec({ artifact_version_id: "latest" }))).rejects.toThrow("EXPORT_FLOATING_VERSION_FORBIDDEN");
    expect(() => assertExportProfile("CMYK")).toThrow("EXPORT_CMYK_NOT_SUPPORTED_V1");
    expect(() => assertExportProfile("DISPLAY_P3")).toThrow("EXPORT_DISPLAY_P3_NOT_VERIFIED_V1");
    expect(() => assertExportFormat("PSD")).toThrow("EXPORT_PSD_NOT_SUPPORTED");
    const hidden = harness(snapshot({ design_document: { document_id: "doc-1", system_prompt: "secret", nodes: {} } }));
    await expect(hidden.engine.start(spec())).rejects.toThrow("EXPORT_SENSITIVE_METADATA_FORBIDDEN");
  });

  it("rejects ephemeral compiler URLs in the durable source snapshot", async () => {
    const h = harness(snapshot({ render_plan: { compiler_version: "1.0.0", document_id: "doc-1", items: [], uri: "https://signed.invalid/x" } }));
    await expect(h.engine.start(spec())).rejects.toThrow("EXPORT_EPHEMERAL_RUNTIME_REF_FORBIDDEN");
  });
});

describe("NODE-49 format and package security", () => {
  it("sanitizes filenames and blocks zip-slip", () => {
    expect(sanitizeExportFilename("  海报:夏日/活动  ")).toBe("海报_夏日_活动");
    expect(() => safeZipEntryName("../../etc/passwd")).toThrow("EXPORT_ZIP_TRAVERSAL_FORBIDDEN");
    expect(() => safeZipEntryName("C:/Windows/system.ini")).toThrow("EXPORT_ZIP_ABSOLUTE_PATH_FORBIDDEN");
    const zip = writeStoreZip([{ name: "文件/海报.txt", bytes: new TextEncoder().encode("ok") }]);
    expect(inspectZipEntries(zip)).toEqual(["文件/海报.txt"]);
  });

  it("writes and independently parses multi-page PDF boxes", () => {
    const pdf = writeRasterPdf([
      { jpeg: new Uint8Array([0xff, 0xd8, 0xff, 0xd9]), width_px: 720, height_px: 720, dpi: 72 },
      { jpeg: new Uint8Array([0xff, 0xd8, 0xff, 0xd9]), width_px: 600, height_px: 300, dpi: 100 },
    ]);
    const inspection = inspectRasterPdf(pdf);
    expect(inspection.page_count).toBe(2);
    expect(inspection.media_boxes).toEqual([{ width_pt: 720, height_pt: 720 }, { width_pt: 432, height_pt: 216 }]);
  });

  it("serializes actual Canvas tx/ty matrices, vector path, image and font fallback", async () => {
    const [page] = await serializer().renderPages(renderableSource(), { variant_id: "svg", frame_ids: ["frame-1"], format: "SVG" });
    expect(page!.svg).toContain("matrix(1 0 0 1 10 10)");
    expect(page!.svg).toContain("<path");
    expect(page!.svg).toContain("data:image/png;base64,");
    expect(page!.svg).toContain('font-family="sans-serif"');
    expect(page!.svg).not.toMatch(/href=["']https?:/);
  });

  it("converts mm/in at DPI and distinguishes SCALE from CROP", async () => {
    const scale = (await serializer().renderPages(renderableSource(), { variant_id: "scale", frame_ids: ["frame-1"], format: "SVG", width: 25.4, height: 12.7, unit: "MM", dpi: 100, resize_mode: "SCALE" }))[0]!;
    expect([scale.width, scale.height]).toEqual([100, 50]);
    expect(scale.svg).toContain('preserveAspectRatio="xMidYMid meet"');
    const crop = (await serializer().renderPages(renderableSource(), { variant_id: "crop", frame_ids: ["frame-1"], format: "SVG", width: 1, height: 2, unit: "IN", dpi: 100, resize_mode: "CROP" }))[0]!;
    expect([crop.width, crop.height]).toEqual([100, 200]);
    expect(crop.svg).toContain('preserveAspectRatio="xMidYMid slice"');
  });

  it("fails closed for print marks not implemented in V1", async () => {
    const codec: ExportRasterCodecPort = { async encodeSvg() { return { bytes: new Uint8Array([0x89]), mime_type: "image/png" }; } };
    const renderer = new CompositeExportRenderer({ svg: serializer(), raster: codec });
    await expect(renderer.render(renderableSource(), { variant_id: "print", frame_ids: ["frame-1"], format: "PNG", bleed: 3 })).rejects.toThrow("EXPORT_PRINT_MARKS_NOT_IMPLEMENTED_V1");
  });

  it("builds a valid PDF from rasterized SVG pages", async () => {
    const codec: ExportRasterCodecPort = { async encodeSvg() { return { bytes: new Uint8Array([0xff, 0xd8, 0xff, 0xd9]), mime_type: "image/jpeg" }; } };
    const renderer = new CompositeExportRenderer({ svg: serializer(), raster: codec });
    const output = await renderer.render(renderableSource(), { variant_id: "pdf", frame_ids: ["frame-1"], format: "PDF", dpi: 72 });
    expect(output.mime_type).toBe("application/pdf");
    expect(inspectRasterPdf(output.bytes).page_count).toBe(1);
  });

  it("validates typed raster worker MIME and decoded dimensions", async () => {
    const codec = new WorkerBackedRasterCodec({ async invoke(request) { return { bytes: new Uint8Array([1, 2, 3]), mime_type: request.format === "WEBP" ? "image/webp" : "image/png", width: request.width, height: request.height }; } });
    await expect(codec.encodeSvg({ svg: "<svg/>", format: "WEBP", width: 120, height: 80, quality: 90 })).resolves.toMatchObject({ mime_type: "image/webp" });
    const invalid = new WorkerBackedRasterCodec({ async invoke() { return { bytes: new Uint8Array([1]), mime_type: "image/png", width: 1, height: 1 }; } });
    await expect(invalid.encodeSvg({ svg: "<svg/>", format: "PNG", width: 2, height: 2, quality: 90 })).rejects.toThrow("EXPORT_RASTER_WORKER_DIMENSIONS_MISMATCH");
  });
});
