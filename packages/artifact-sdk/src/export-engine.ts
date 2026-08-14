import {
  EXPORT_ENGINE_VERSION,
  type ExportArtifactPort,
  type ExportAuthorizationPort,
  type ExportDownloadAuditPort,
  type ExportDownloadSignerPort,
  type ExportEventPort,
  type ExportFileRecord,
  type ExportJob,
  type ExportJobRepository,
  type ExportManifest,
  type ExportObjectStore,
  type ExportRendererPort,
  type ExportSourcePort,
  type ExportSpec,
  type ExportValidationEvidencePort,
  type ExportVariant,
} from "./export-engine-types";
import { canonicalExportJson, exportFingerprint, exportManifestHash, stableExportFiles } from "./export-hashing";
import { inspectRasterPdf } from "./export-pdf";
import { assertExportFormat, assertExportProfile, safeZipEntryName, sanitizeExportFilename } from "./export-security";
import { inspectZipEntries, writeStoreZip, type ZipEntry } from "./export-zip";

function addSeconds(iso: string, seconds: number): string {
  return new Date(new Date(iso).getTime() + seconds * 1000).toISOString();
}
function exportJobId(organizationId: string, fingerprint: string): string { return `export-job:${organizationId}:${fingerprint}` }
function extension(format: ExportVariant["format"]): string { return { PNG: "png", JPEG: "jpg", WEBP: "webp", SVG: "svg", PDF: "pdf", LUMI_PACKAGE: "lumi.zip", ZIP: "zip" }[format] }
function mime(format: ExportVariant["format"]): string { return { PNG: "image/png", JPEG: "image/jpeg", WEBP: "image/webp", SVG: "image/svg+xml", PDF: "application/pdf", LUMI_PACKAGE: "application/zip", ZIP: "application/zip" }[format] }
function fileName(spec: ExportSpec, variant: ExportVariant): string {
  const base = sanitizeExportFilename(variant.filename ?? spec.filename_template, "export"); const ext = extension(variant.format);
  return base.toLowerCase().endsWith(`.${ext}`) ? base : `${base}.${ext}`;
}
function validateSpec(spec: ExportSpec): void {
  if (!spec.organization_id || !spec.project_id || !spec.requested_by || !spec.operation_id) throw new Error("EXPORT_IDENTITY_REQUIRED");
  if (!spec.artifact_version_id || !spec.design_document_version_id) throw new Error("EXPORT_EXACT_VERSION_REQUIRED");
  if (/latest|head|current/i.test(spec.artifact_version_id) || /latest|head|current/i.test(spec.design_document_version_id)) throw new Error("EXPORT_FLOATING_VERSION_FORBIDDEN");
  if (!spec.filename_template.trim()) throw new Error("EXPORT_FILENAME_TEMPLATE_REQUIRED");
  if (!spec.variants.length) throw new Error("EXPORT_VARIANTS_REQUIRED");
  if (new Set(spec.variants.map((variant) => variant.variant_id)).size !== spec.variants.length) throw new Error("EXPORT_VARIANT_ID_DUPLICATE");
  if (!Number.isInteger(spec.retention_seconds) || spec.retention_seconds < 60 || spec.retention_seconds > 604800) throw new Error("EXPORT_RETENTION_INVALID");
  for (const variant of spec.variants) {
    if (!variant.variant_id) throw new Error("EXPORT_VARIANT_ID_REQUIRED");
    assertExportFormat(variant.format); assertExportProfile(variant.color_profile);
    if ((variant.bleed ?? 0) !== 0 || variant.crop_marks === true) throw new Error("EXPORT_PRINT_MARKS_NOT_IMPLEMENTED_V1");
    if (!variant.frame_ids.length && variant.format !== "LUMI_PACKAGE" && variant.format !== "ZIP") throw new Error("EXPORT_FRAME_IDS_REQUIRED");
    if ((variant.width === undefined) !== (variant.height === undefined)) throw new Error("EXPORT_TARGET_DIMENSIONS_PAIR_REQUIRED");
    if (variant.resize_mode === "CROP" && (variant.width === undefined || variant.height === undefined)) throw new Error("EXPORT_CROP_TARGET_DIMENSIONS_REQUIRED");
    for (const dimension of [variant.width, variant.height]) if (dimension !== undefined && (!Number.isFinite(dimension) || dimension <= 0)) throw new Error("EXPORT_TARGET_DIMENSIONS_INVALID");
    if (variant.scale !== undefined && (!Number.isFinite(variant.scale) || variant.scale <= 0 || variant.scale > 16)) throw new Error("EXPORT_SCALE_INVALID");
    if (variant.quality !== undefined && (!Number.isInteger(variant.quality) || variant.quality < 1 || variant.quality > 100)) throw new Error("EXPORT_QUALITY_INVALID");
    if (variant.dpi !== undefined && (!Number.isInteger(variant.dpi) || variant.dpi < 36 || variant.dpi > 1200)) throw new Error("EXPORT_DPI_INVALID");
  }
}
async function bytesSha256(bytes: Uint8Array): Promise<string> {
  const copy = Uint8Array.from(bytes); const digest = await crypto.subtle.digest("SHA-256", copy.buffer);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}
function storageKey(job: ExportJob, variant: ExportVariant, filename: string): string {
  return `org/${job.organization_id}/exports/${job.export_fingerprint}/${sanitizeExportFilename(variant.variant_id, "variant")}/${safeZipEntryName(filename)}`;
}
function semanticManifestSpec(spec: ExportSpec): Readonly<Record<string, unknown>> {
  return { artifact_version_id: spec.artifact_version_id, design_document_version_id: spec.design_document_version_id, filename_template: spec.filename_template, include_manifest: spec.include_manifest, retention_seconds: spec.retention_seconds, variants: spec.variants.map((variant) => ({ ...variant, frame_ids: [...variant.frame_ids] })) };
}
function hasPrefix(bytes: Uint8Array, prefix: readonly number[]): boolean { return prefix.every((value, index) => bytes[index] === value) }
function validateStoredFormat(file: ExportFileRecord, bytes: Uint8Array): Readonly<Record<string, unknown>> {
  if (!bytes.length) throw new Error("EXPORT_STORED_FILE_EMPTY");
  if (file.mime_type === "image/png") {
    if (!hasPrefix(bytes, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) throw new Error("EXPORT_PNG_SIGNATURE_INVALID");
    return { mime_type: file.mime_type, signature: "PNG" };
  }
  if (file.mime_type === "image/jpeg") {
    if (!hasPrefix(bytes, [0xff, 0xd8]) || bytes.at(-2) !== 0xff || bytes.at(-1) !== 0xd9) throw new Error("EXPORT_JPEG_SIGNATURE_INVALID");
    return { mime_type: file.mime_type, signature: "JPEG" };
  }
  if (file.mime_type === "image/webp") {
    const ascii = new TextDecoder("ascii");
    if (ascii.decode(bytes.slice(0, 4)) !== "RIFF" || ascii.decode(bytes.slice(8, 12)) !== "WEBP") throw new Error("EXPORT_WEBP_SIGNATURE_INVALID");
    return { mime_type: file.mime_type, signature: "WEBP" };
  }
  if (file.mime_type === "image/svg+xml") {
    const text = new TextDecoder().decode(bytes);
    if (!text.startsWith("<svg") || /<script\b/i.test(text) || /\b(?:href|src)=["']https?:/i.test(text)) throw new Error("EXPORT_SVG_STORED_INVALID");
    return { mime_type: file.mime_type, safe_svg: true };
  }
  if (file.mime_type === "application/pdf") {
    const inspection = inspectRasterPdf(bytes);
    if (file.page_count !== undefined && inspection.page_count !== file.page_count) throw new Error("EXPORT_PDF_STORED_PAGE_COUNT_MISMATCH");
    return { mime_type: file.mime_type, page_count: inspection.page_count, media_boxes: inspection.media_boxes };
  }
  if (file.mime_type === "application/zip") {
    const names = inspectZipEntries(bytes);
    return { mime_type: file.mime_type, entry_count: names.length };
  }
  if (file.mime_type === "application/json") {
    JSON.parse(new TextDecoder().decode(bytes));
    return { mime_type: file.mime_type, json: true };
  }
  throw new Error(`EXPORT_STORED_MIME_UNSUPPORTED:${file.mime_type}`);
}

export class ExportEngine {
  readonly #source: ExportSourcePort;
  readonly #jobs: ExportJobRepository;
  readonly #renderer: ExportRendererPort;
  readonly #store: ExportObjectStore;
  readonly #artifacts: ExportArtifactPort;
  readonly #events: ExportEventPort;
  readonly #validation?: ExportValidationEvidencePort;
  readonly #now: () => string;

  constructor(args: { readonly source: ExportSourcePort; readonly jobs: ExportJobRepository; readonly renderer: ExportRendererPort; readonly store: ExportObjectStore; readonly artifacts: ExportArtifactPort; readonly events: ExportEventPort; readonly validation?: ExportValidationEvidencePort; readonly now?: () => string }) {
    this.#source = args.source; this.#jobs = args.jobs; this.#renderer = args.renderer; this.#store = args.store; this.#artifacts = args.artifacts; this.#events = args.events; this.#validation = args.validation; this.#now = args.now ?? (() => new Date().toISOString());
  }

  async start(spec: ExportSpec): Promise<ExportJob> {
    validateSpec(spec);
    const existing = await this.#jobs.findByOperation(spec.organization_id, spec.operation_id);
    if (existing) {
      const source = await this.#source.resolveExactSnapshot(spec); const fingerprint = await exportFingerprint(source, spec);
      if (existing.export_fingerprint !== fingerprint) throw new Error("EXPORT_OPERATION_SEMANTIC_CONFLICT");
      return existing;
    }
    const source = await this.#source.resolveExactSnapshot(spec);
    if (source.organization_id !== spec.organization_id || source.project_id !== spec.project_id || source.artifact_version_id !== spec.artifact_version_id || source.design_document_version_id !== spec.design_document_version_id) throw new Error("EXPORT_SOURCE_SCOPE_OR_VERSION_MISMATCH");
    const fingerprint = await exportFingerprint(source, spec); const now = this.#now(); const expiresAt = addSeconds(now, spec.retention_seconds);
    const reusable = await this.#jobs.findReadyByFingerprint(spec.organization_id, fingerprint, expiresAt);
    if (reusable) return reusable;
    const job: ExportJob = { export_job_id: exportJobId(spec.organization_id, fingerprint), organization_id: spec.organization_id, project_id: spec.project_id, operation_id: spec.operation_id, export_fingerprint: fingerprint, source, spec, status: "PENDING", progress: 0, files: [], created_at: now, expires_at: expiresAt };
    await this.#jobs.save(job);
    await this.#events.emit("export.created", { export_job_id: job.export_job_id, artifact_version_id: source.artifact_version_id, design_document_version_id: source.design_document_version_id, export_fingerprint: fingerprint });
    return job;
  }

  async execute(organizationId: string, exportJobIdValue: string): Promise<ExportJob> {
    const current = await this.#jobs.get(organizationId, exportJobIdValue);
    if (!current) throw new Error("EXPORT_JOB_NOT_FOUND");
    if (current.status === "READY" || current.status === "FAILED" || current.status === "EXPIRED") return current;
    if (current.source.artifact_version_id !== current.spec.artifact_version_id || current.source.design_document_version_id !== current.spec.design_document_version_id) throw new Error("EXPORT_PINNED_SOURCE_CORRUPTED");
    let job: ExportJob = { ...current, status: "RENDERING", progress: 5 }; await this.#jobs.save(job); await this.#events.emit("export.rendering", { export_job_id: job.export_job_id });
    try {
      const regularVariants = job.spec.variants.filter((variant) => variant.format !== "ZIP" && variant.format !== "LUMI_PACKAGE"); const renderedFiles: ExportFileRecord[] = [];
      for (let index = 0; index < regularVariants.length; index += 1) {
        const variant = regularVariants[index]!; const payload = await this.#renderer.render(job.source, variant);
        if (!payload.bytes.length || payload.mime_type !== mime(variant.format)) throw new Error("EXPORT_RENDER_PAYLOAD_INVALID");
        const filename = fileName(job.spec, variant); const persisted = await this.#store.put(storageKey(job, variant, filename), payload.bytes, payload.mime_type); const localChecksum = await bytesSha256(payload.bytes);
        if (persisted.checksum_sha256 !== localChecksum || persisted.size_bytes !== payload.bytes.length) throw new Error("EXPORT_STORAGE_CHECKSUM_MISMATCH");
        renderedFiles.push({ file_id: `export-file:${job.export_fingerprint}:${variant.variant_id}`, variant_id: variant.variant_id, storage_key: persisted.storage_key, filename, mime_type: payload.mime_type, checksum_sha256: persisted.checksum_sha256, size_bytes: persisted.size_bytes, ...(payload.width !== undefined ? { width: payload.width } : {}), ...(payload.height !== undefined ? { height: payload.height } : {}), ...(payload.page_count !== undefined ? { page_count: payload.page_count } : {}), ...(payload.metadata ? { metadata: payload.metadata } : {}) });
        job = { ...job, files: [...renderedFiles], progress: 10 + Math.round(((index + 1) / Math.max(regularVariants.length, 1)) * 55) }; await this.#jobs.save(job);
        await this.#events.emit("export.variant_ready", { export_job_id: job.export_job_id, variant_id: variant.variant_id, checksum_sha256: persisted.checksum_sha256 });
      }
      job = { ...job, status: "PACKAGING", progress: 70 }; await this.#jobs.save(job);
      const manifestWithoutHash: Omit<ExportManifest, "manifest_sha256"> = { schema_version: "1.0", export_engine_version: EXPORT_ENGINE_VERSION, export_job_id: job.export_job_id, export_fingerprint: job.export_fingerprint, organization_id: job.organization_id, project_id: job.project_id, artifact_id: job.source.artifact_id, artifact_version_id: job.source.artifact_version_id, design_document_version_id: job.source.design_document_version_id, source_content_hash: job.source.content_hash, compiler: job.source.compiler_provenance, spec: semanticManifestSpec(job.spec), files: stableExportFiles(renderedFiles), source_provenance_refs: [...job.source.source_provenance_refs].sort(), brand_rule_set_version: job.source.brand_rule_set_version ?? null, rights_summary: job.source.rights_summary, model_refs: [...job.source.model_refs].sort(), created_at: job.created_at };
      const manifest: ExportManifest = { ...manifestWithoutHash, manifest_sha256: await exportManifestHash(manifestWithoutHash) }; const manifestBytes = new TextEncoder().encode(canonicalExportJson(manifest)); let manifestFile: ExportFileRecord | undefined;
      if (job.spec.include_manifest) {
        const variant: ExportVariant = { variant_id: "manifest", frame_ids: [], format: "ZIP" }; const filename = "manifest.json"; const persisted = await this.#store.put(storageKey(job, variant, filename), manifestBytes, "application/json");
        if (persisted.checksum_sha256 !== await bytesSha256(manifestBytes)) throw new Error("EXPORT_MANIFEST_CHECKSUM_MISMATCH");
        manifestFile = { file_id: `export-file:${job.export_fingerprint}:manifest`, variant_id: "manifest", storage_key: persisted.storage_key, filename, mime_type: "application/json", checksum_sha256: persisted.checksum_sha256, size_bytes: persisted.size_bytes };
      }
      const packageFiles: ExportFileRecord[] = [];
      for (const variant of job.spec.variants.filter((item) => item.format === "ZIP" || item.format === "LUMI_PACKAGE")) {
        const entries: ZipEntry[] = [];
        if (variant.format === "ZIP") { for (const file of renderedFiles) entries.push({ name: `files/${file.filename}`, bytes: await this.#store.get(file.storage_key) }); entries.push({ name: "manifest.json", bytes: manifestBytes }); }
        else { entries.push({ name: "lumi/manifest.json", bytes: manifestBytes }, { name: "lumi/design-document.json", bytes: new TextEncoder().encode(canonicalExportJson(job.source.design_document)) }, { name: "lumi/compiler-provenance.json", bytes: new TextEncoder().encode(canonicalExportJson(job.source.compiler_provenance)) }, { name: "lumi/rights-summary.json", bytes: new TextEncoder().encode(canonicalExportJson(job.source.rights_summary)) }); if (job.source.project_snapshot) entries.push({ name: "lumi/project-snapshot.json", bytes: new TextEncoder().encode(canonicalExportJson(job.source.project_snapshot)) }); for (const file of renderedFiles) entries.push({ name: `lumi/exports/${file.filename}`, bytes: await this.#store.get(file.storage_key) }); }
        const packageBytes = writeStoreZip(entries); inspectZipEntries(packageBytes); const filename = fileName(job.spec, variant); const persisted = await this.#store.put(storageKey(job, variant, filename), packageBytes, "application/zip");
        if (persisted.checksum_sha256 !== await bytesSha256(packageBytes)) throw new Error("EXPORT_PACKAGE_CHECKSUM_MISMATCH");
        packageFiles.push({ file_id: `export-file:${job.export_fingerprint}:${variant.variant_id}`, variant_id: variant.variant_id, storage_key: persisted.storage_key, filename, mime_type: "application/zip", checksum_sha256: persisted.checksum_sha256, size_bytes: persisted.size_bytes });
      }
      const allFiles = [...renderedFiles, ...packageFiles]; job = { ...job, status: "VALIDATING", progress: 90, files: allFiles, manifest, ...(manifestFile ? { manifest_file: manifestFile } : {}), ...(packageFiles[0] ? { package_file: packageFiles[0] } : {}) }; await this.#jobs.save(job);
      for (const file of [...allFiles, ...(manifestFile ? [manifestFile] : [])]) {
        const bytes = await this.#store.get(file.storage_key); const checksum = await bytesSha256(bytes);
        if (checksum !== file.checksum_sha256) throw new Error("EXPORT_READBACK_CHECKSUM_MISMATCH");
        await this.#validation?.record({ organization_id: job.organization_id, export_job_id: job.export_job_id, export_file_id: file.file_id, validator: "sha256-readback", status: "PASS", details: { checksum_sha256: checksum, size_bytes: bytes.length } });
        const details = validateStoredFormat(file, bytes);
        await this.#validation?.record({ organization_id: job.organization_id, export_job_id: job.export_job_id, export_file_id: file.file_id, validator: "format-structure", status: "PASS", details });
      }
      await this.#artifacts.persistExport({ job, files: allFiles, manifest, ...(packageFiles[0] ? { package_file: packageFiles[0] } : {}) });
      const ready: ExportJob = { ...job, status: "READY", progress: 100 }; await this.#jobs.save(ready); await this.#events.emit("export.ready", { export_job_id: ready.export_job_id, file_count: ready.files.length, manifest_sha256: manifest.manifest_sha256 }); return ready;
    } catch (error) {
      const failed: ExportJob = { ...job, status: "FAILED", error_code: error instanceof Error ? error.message : "EXPORT_UNKNOWN_FAILURE" }; await this.#jobs.save(failed); await this.#events.emit("export.failed", { export_job_id: failed.export_job_id, error_code: failed.error_code ?? "EXPORT_UNKNOWN_FAILURE" }); return failed;
    }
  }
}

export class ExportDownloadService {
  readonly #jobs: ExportJobRepository;
  readonly #authorization: ExportAuthorizationPort;
  readonly #signer: ExportDownloadSignerPort;
  readonly #audit: ExportDownloadAuditPort;
  readonly #now: () => string;

  constructor(args: { readonly jobs: ExportJobRepository; readonly authorization: ExportAuthorizationPort; readonly signer: ExportDownloadSignerPort; readonly audit: ExportDownloadAuditPort; readonly now?: () => string }) {
    this.#jobs = args.jobs; this.#authorization = args.authorization; this.#signer = args.signer; this.#audit = args.audit; this.#now = args.now ?? (() => new Date().toISOString());
  }

  async download(args: { readonly organization_id: string; readonly actor_id: string; readonly export_job_id: string; readonly file_id: string; readonly expires_seconds?: number }): Promise<{ readonly url: string; readonly expires_at: string; readonly filename: string }> {
    const job = await this.#jobs.get(args.organization_id, args.export_job_id); if (!job || job.status !== "READY") throw new Error("EXPORT_DOWNLOAD_NOT_READY"); if (job.expires_at <= this.#now()) throw new Error("EXPORT_DOWNLOAD_EXPIRED");
    const file = [...job.files, ...(job.manifest_file ? [job.manifest_file] : [])].find((item) => item.file_id === args.file_id); if (!file) throw new Error("EXPORT_DOWNLOAD_FILE_NOT_FOUND");
    const allowed = await this.#authorization.canDownload({ organization_id: job.organization_id, project_id: job.project_id, actor_id: args.actor_id, export_job_id: job.export_job_id, file });
    if (!allowed) { await this.#audit.record({ organization_id: job.organization_id, export_job_id: job.export_job_id, export_file_id: file.file_id, actor_id: args.actor_id, decision: "DENIED" }); throw new Error("EXPORT_DOWNLOAD_FORBIDDEN"); }
    const ttl = args.expires_seconds ?? 300; if (!Number.isInteger(ttl) || ttl < 30 || ttl > 900) throw new Error("EXPORT_DOWNLOAD_TTL_INVALID");
    const signed = await this.#signer.sign({ storage_key: file.storage_key, filename: file.filename, expires_seconds: ttl });
    await this.#audit.record({ organization_id: job.organization_id, export_job_id: job.export_job_id, export_file_id: file.file_id, actor_id: args.actor_id, decision: "ALLOWED", signed_ttl_seconds: ttl });
    return { ...signed, filename: file.filename };
  }
}
