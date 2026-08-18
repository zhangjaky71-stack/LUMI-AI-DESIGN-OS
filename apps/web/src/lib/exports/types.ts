export type ExportFormat = "ORIGINAL" | "PNG" | "JPEG" | "MP4" | "PDF" | "PPTX";
export type ExportJobStatus = "PENDING" | "RENDERING" | "PACKAGING" | "VALIDATING" | "READY" | "FAILED" | "CANCELLED";

export type ExportFormatCapability = {
  format: ExportFormat;
  label: string;
  outputExtension: string;
  copyThrough: boolean;
};

export type ExportCapabilities = {
  artifactVersionId: string;
  approved: boolean;
  sourceMimeType: string;
  formats: readonly ExportFormatCapability[];
  supportsResize: boolean;
  supportsQuality: boolean;
  supportsAlpha: boolean;
  supportsPrintOptions: boolean;
  supportsAiAdapt: boolean;
  supportsBatchZip: boolean;
  maxBatchItems: number;
};

export type ExportJobItem = { artifactVersionId: string; targetFormat: ExportFormat; outputName: string };
export type ExportOutput = {
  name: string;
  mimeType: string;
  sizeBytes: number;
  checksumSha256: string;
  rendererVersion: string;
  sourceArtifactId: string;
  sourceArtifactVersionId: string;
};
export type ExportManifestEntry = {
  name: string;
  mimeType: string;
  sizeBytes: number;
  checksumSha256: string;
  artifactId: string;
  artifactVersionId: string;
  rendererVersion: string;
};
export type ExportManifest = {
  schemaVersion: string;
  exportJobId: string;
  operationId: string;
  createdAt: string;
  exporterVersion: string;
  entries: readonly ExportManifestEntry[];
};
export type ExportPackage = {
  packageId: string;
  filename: string;
  mimeType: string;
  sizeBytes: number;
  checksumSha256: string;
  isArchive: boolean;
};
export type ExportJob = {
  jobId: string;
  projectId: string;
  taskId: string;
  operationId: string;
  status: ExportJobStatus;
  items: readonly ExportJobItem[];
  outputs: readonly ExportOutput[];
  package: ExportPackage | null;
  manifest: ExportManifest | null;
  errorCode: string | null;
};
export type ExportDownloadGrant = {
  jobId: string;
  packageId: string;
  filename: string;
  mimeType: string;
  sizeBytes: number;
  checksumSha256: string;
  expiresAt: string;
  url: string;
};

export function parseExportCapabilities(value: unknown): ExportCapabilities {
  const record = object(value, "EXPORT_CAPABILITIES_INVALID");
  return {
    artifactVersionId: requiredString(record.artifact_version_id ?? record.artifactVersionId, "EXPORT_CAPABILITY_VERSION_REQUIRED"),
    approved: booleanValue(record.approved, "EXPORT_CAPABILITY_APPROVED_REQUIRED"),
    sourceMimeType: requiredString(record.source_mime_type ?? record.sourceMimeType, "EXPORT_CAPABILITY_MIME_REQUIRED"),
    formats: array(record.formats, "EXPORT_CAPABILITY_FORMATS_INVALID").map((item) => {
      const format = object(item, "EXPORT_CAPABILITY_FORMAT_INVALID");
      return {
        format: exportFormat(format.format),
        label: requiredString(format.label, "EXPORT_CAPABILITY_LABEL_REQUIRED"),
        outputExtension: requiredString(format.output_extension ?? format.outputExtension, "EXPORT_CAPABILITY_EXTENSION_REQUIRED"),
        copyThrough: booleanValue(format.copy_through ?? format.copyThrough, "EXPORT_CAPABILITY_COPY_FLAG_REQUIRED"),
      };
    }),
    supportsResize: booleanValue(record.supports_resize ?? record.supportsResize, "EXPORT_RESIZE_FLAG_REQUIRED"),
    supportsQuality: booleanValue(record.supports_quality ?? record.supportsQuality, "EXPORT_QUALITY_FLAG_REQUIRED"),
    supportsAlpha: booleanValue(record.supports_alpha ?? record.supportsAlpha, "EXPORT_ALPHA_FLAG_REQUIRED"),
    supportsPrintOptions: booleanValue(record.supports_print_options ?? record.supportsPrintOptions, "EXPORT_PRINT_FLAG_REQUIRED"),
    supportsAiAdapt: booleanValue(record.supports_ai_adapt ?? record.supportsAiAdapt, "EXPORT_ADAPT_FLAG_REQUIRED"),
    supportsBatchZip: booleanValue(record.supports_batch_zip ?? record.supportsBatchZip, "EXPORT_BATCH_FLAG_REQUIRED"),
    maxBatchItems: integer(record.max_batch_items ?? record.maxBatchItems, "EXPORT_BATCH_LIMIT_INVALID", 1),
  };
}

export function parseExportJob(value: unknown): ExportJob {
  const record = object(value, "EXPORT_JOB_INVALID");
  return {
    jobId: requiredString(record.job_id ?? record.jobId, "EXPORT_JOB_ID_REQUIRED"),
    projectId: requiredString(record.project_id ?? record.projectId, "EXPORT_PROJECT_ID_REQUIRED"),
    taskId: requiredString(record.task_id ?? record.taskId, "EXPORT_TASK_ID_REQUIRED"),
    operationId: requiredString(record.operation_id ?? record.operationId, "EXPORT_OPERATION_ID_REQUIRED"),
    status: enumValue(record.status, ["PENDING", "RENDERING", "PACKAGING", "VALIDATING", "READY", "FAILED", "CANCELLED"] as const, "EXPORT_STATUS_INVALID"),
    items: array(record.items, "EXPORT_ITEMS_INVALID").map(parseItem),
    outputs: array(record.outputs, "EXPORT_OUTPUTS_INVALID").map(parseOutput),
    package: nullableRecord(record.package, parsePackage),
    manifest: nullableRecord(record.manifest, parseManifest),
    errorCode: nullableString(record.error_code ?? record.errorCode),
  };
}

export function parseExportDownloadGrant(value: unknown): ExportDownloadGrant {
  const record = object(value, "EXPORT_DOWNLOAD_INVALID");
  return {
    jobId: requiredString(record.job_id ?? record.jobId, "EXPORT_DOWNLOAD_JOB_REQUIRED"),
    packageId: requiredString(record.package_id ?? record.packageId, "EXPORT_DOWNLOAD_PACKAGE_REQUIRED"),
    filename: requiredString(record.filename, "EXPORT_DOWNLOAD_FILENAME_REQUIRED"),
    mimeType: requiredString(record.mime_type ?? record.mimeType, "EXPORT_DOWNLOAD_MIME_REQUIRED"),
    sizeBytes: integer(record.size_bytes ?? record.sizeBytes, "EXPORT_DOWNLOAD_SIZE_INVALID", 0),
    checksumSha256: sha256(record.checksum_sha256 ?? record.checksumSha256),
    expiresAt: requiredString(record.expires_at ?? record.expiresAt, "EXPORT_DOWNLOAD_EXPIRY_REQUIRED"),
    url: requiredString(record.url, "EXPORT_DOWNLOAD_URL_REQUIRED"),
  };
}

function parseItem(value: unknown): ExportJobItem {
  const record = object(value, "EXPORT_ITEM_INVALID");
  return {
    artifactVersionId: requiredString(record.artifact_version_id ?? record.artifactVersionId, "EXPORT_ITEM_VERSION_REQUIRED"),
    targetFormat: exportFormat(record.target_format ?? record.targetFormat),
    outputName: requiredString(record.output_name ?? record.outputName, "EXPORT_ITEM_NAME_REQUIRED"),
  };
}
function parseOutput(value: unknown): ExportOutput {
  const record = object(value, "EXPORT_OUTPUT_INVALID");
  return {
    name: requiredString(record.name, "EXPORT_OUTPUT_NAME_REQUIRED"),
    mimeType: requiredString(record.mime_type ?? record.mimeType, "EXPORT_OUTPUT_MIME_REQUIRED"),
    sizeBytes: integer(record.size_bytes ?? record.sizeBytes, "EXPORT_OUTPUT_SIZE_INVALID", 0),
    checksumSha256: sha256(record.checksum_sha256 ?? record.checksumSha256),
    rendererVersion: requiredString(record.renderer_version ?? record.rendererVersion, "EXPORT_OUTPUT_RENDERER_REQUIRED"),
    sourceArtifactId: requiredString(record.source_artifact_id ?? record.sourceArtifactId, "EXPORT_OUTPUT_ARTIFACT_REQUIRED"),
    sourceArtifactVersionId: requiredString(record.source_artifact_version_id ?? record.sourceArtifactVersionId, "EXPORT_OUTPUT_VERSION_REQUIRED"),
  };
}
function parsePackage(value: Record<string, unknown>): ExportPackage {
  return {
    packageId: requiredString(value.package_id ?? value.packageId, "EXPORT_PACKAGE_ID_REQUIRED"),
    filename: requiredString(value.filename, "EXPORT_PACKAGE_FILENAME_REQUIRED"),
    mimeType: requiredString(value.mime_type ?? value.mimeType, "EXPORT_PACKAGE_MIME_REQUIRED"),
    sizeBytes: integer(value.size_bytes ?? value.sizeBytes, "EXPORT_PACKAGE_SIZE_INVALID", 0),
    checksumSha256: sha256(value.checksum_sha256 ?? value.checksumSha256),
    isArchive: booleanValue(value.is_archive ?? value.isArchive, "EXPORT_PACKAGE_ARCHIVE_FLAG_REQUIRED"),
  };
}
function parseManifest(value: Record<string, unknown>): ExportManifest {
  return {
    schemaVersion: requiredString(value.schema_version ?? value.schemaVersion, "EXPORT_MANIFEST_SCHEMA_REQUIRED"),
    exportJobId: requiredString(value.export_job_id ?? value.exportJobId, "EXPORT_MANIFEST_JOB_REQUIRED"),
    operationId: requiredString(value.operation_id ?? value.operationId, "EXPORT_MANIFEST_OPERATION_REQUIRED"),
    createdAt: requiredString(value.created_at ?? value.createdAt, "EXPORT_MANIFEST_TIME_REQUIRED"),
    exporterVersion: requiredString(value.exporter_version ?? value.exporterVersion, "EXPORT_MANIFEST_EXPORTER_REQUIRED"),
    entries: array(value.entries, "EXPORT_MANIFEST_ENTRIES_INVALID").map((entry) => {
      const item = object(entry, "EXPORT_MANIFEST_ENTRY_INVALID");
      return {
        name: requiredString(item.name, "EXPORT_MANIFEST_ENTRY_NAME_REQUIRED"),
        mimeType: requiredString(item.mime_type ?? item.mimeType, "EXPORT_MANIFEST_ENTRY_MIME_REQUIRED"),
        sizeBytes: integer(item.size_bytes ?? item.sizeBytes, "EXPORT_MANIFEST_ENTRY_SIZE_INVALID", 0),
        checksumSha256: sha256(item.checksum_sha256 ?? item.checksumSha256),
        artifactId: requiredString(item.artifact_id ?? item.artifactId, "EXPORT_MANIFEST_ENTRY_ARTIFACT_REQUIRED"),
        artifactVersionId: requiredString(item.artifact_version_id ?? item.artifactVersionId, "EXPORT_MANIFEST_ENTRY_VERSION_REQUIRED"),
        rendererVersion: requiredString(item.renderer_version ?? item.rendererVersion, "EXPORT_MANIFEST_ENTRY_RENDERER_REQUIRED"),
      };
    }),
  };
}

function exportFormat(value: unknown): ExportFormat { return enumValue(value, ["ORIGINAL", "PNG", "JPEG", "MP4", "PDF", "PPTX"] as const, "EXPORT_FORMAT_INVALID"); }
function object(value: unknown, code: string): Record<string, unknown> { if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(code); return value as Record<string, unknown>; }
function array(value: unknown, code: string): unknown[] { if (!Array.isArray(value)) throw new Error(code); return value; }
function requiredString(value: unknown, code: string): string { if (typeof value !== "string" || !value.trim()) throw new Error(code); return value; }
function nullableString(value: unknown): string | null { if (value === undefined || value === null) return null; if (typeof value !== "string") throw new Error("EXPORT_OPTIONAL_STRING_INVALID"); return value; }
function booleanValue(value: unknown, code: string): boolean { if (typeof value !== "boolean") throw new Error(code); return value; }
function integer(value: unknown, code: string, min: number): number { if (!Number.isInteger(value) || (value as number) < min) throw new Error(code); return value as number; }
function sha256(value: unknown): string { const text = requiredString(value, "EXPORT_SHA_REQUIRED"); if (!/^[0-9a-f]{64}$/.test(text)) throw new Error("EXPORT_SHA_INVALID"); return text; }
function nullableRecord<T>(value: unknown, parser: (value: Record<string, unknown>) => T): T | null { if (value === undefined || value === null) return null; return parser(object(value, "EXPORT_OPTIONAL_RECORD_INVALID")); }
function enumValue<const T extends readonly string[]>(value: unknown, allowed: T, code: string): T[number] { if (typeof value !== "string" || !(allowed as readonly string[]).includes(value)) throw new Error(code); return value as T[number]; }
