import type { CompilerArtifactProvenance } from "./types";

export const EXPORT_ENGINE_VERSION = "1.0.0";

export type ExportFormat =
  | "PNG"
  | "JPEG"
  | "WEBP"
  | "SVG"
  | "PDF"
  | "LUMI_PACKAGE"
  | "ZIP";

export type ExportJobStatus =
  | "PENDING"
  | "RENDERING"
  | "PACKAGING"
  | "VALIDATING"
  | "READY"
  | "FAILED"
  | "EXPIRED";

export type ExportResizeMode = "SCALE" | "CROP";
export type ExportColorProfile = "SRGB" | "DISPLAY_P3" | "CMYK";
export type ExportUnit = "PX" | "MM" | "IN";

export interface ExportSourceSnapshot {
  readonly organization_id: string;
  readonly project_id: string;
  readonly artifact_id: string;
  readonly artifact_version_id: string;
  readonly design_document_version_id: string;
  readonly content_hash: string;
  readonly constraint_snapshot_hash: string;
  readonly compiler_provenance: CompilerArtifactProvenance;
  /** Exact immutable Design IR snapshot. Export must never re-read floating latest. */
  readonly design_document: unknown;
  /** NODE-41 disposable derivative compiled from the same exact Design IR snapshot. */
  readonly render_plan: unknown;
  readonly brand_rule_set_version?: string | null;
  readonly rights_summary: Readonly<Record<string, unknown>>;
  readonly model_refs: readonly string[];
  readonly source_provenance_refs: readonly string[];
  readonly project_snapshot?: Readonly<Record<string, unknown>>;
}

export interface ExportVariant {
  readonly variant_id: string;
  readonly frame_ids: readonly string[];
  readonly format: ExportFormat;
  readonly width?: number;
  readonly height?: number;
  readonly scale?: number;
  readonly resize_mode?: ExportResizeMode;
  readonly quality?: number;
  readonly transparent_background?: boolean;
  readonly background?: string;
  readonly color_profile?: ExportColorProfile;
  readonly dpi?: number;
  readonly unit?: ExportUnit;
  readonly bleed?: number;
  readonly crop_marks?: boolean;
  readonly filename?: string;
}

export interface ExportSpec {
  readonly organization_id: string;
  readonly project_id: string;
  readonly requested_by: string;
  readonly operation_id: string;
  readonly artifact_version_id: string;
  readonly design_document_version_id: string;
  readonly variants: readonly ExportVariant[];
  readonly filename_template: string;
  readonly include_manifest: boolean;
  readonly retention_seconds: number;
}

export interface ExportFileRecord {
  readonly file_id: string;
  readonly variant_id: string;
  readonly storage_key: string;
  readonly filename: string;
  readonly mime_type: string;
  readonly checksum_sha256: string;
  readonly size_bytes: number;
  readonly width?: number;
  readonly height?: number;
  readonly page_count?: number;
  readonly metadata?: Readonly<Record<string, unknown>>;
}

export interface ExportManifestFile {
  readonly filename: string;
  readonly mime_type: string;
  readonly checksum_sha256: string;
  readonly size_bytes: number;
  readonly width?: number;
  readonly height?: number;
  readonly page_count?: number;
}

export interface ExportManifest {
  readonly schema_version: "1.0";
  readonly export_engine_version: string;
  readonly export_job_id: string;
  readonly export_fingerprint: string;
  readonly organization_id: string;
  readonly project_id: string;
  readonly artifact_id: string;
  readonly artifact_version_id: string;
  readonly design_document_version_id: string;
  readonly source_content_hash: string;
  readonly compiler: CompilerArtifactProvenance;
  readonly spec: Readonly<Record<string, unknown>>;
  readonly files: readonly ExportManifestFile[];
  readonly source_provenance_refs: readonly string[];
  readonly brand_rule_set_version: string | null;
  readonly rights_summary: Readonly<Record<string, unknown>>;
  readonly model_refs: readonly string[];
  readonly created_at: string;
  readonly manifest_sha256: string;
}

export interface ExportJob {
  readonly export_job_id: string;
  readonly organization_id: string;
  readonly project_id: string;
  readonly operation_id: string;
  readonly export_fingerprint: string;
  readonly source: ExportSourceSnapshot;
  readonly spec: ExportSpec;
  readonly status: ExportJobStatus;
  readonly progress: number;
  readonly files: readonly ExportFileRecord[];
  readonly manifest?: ExportManifest;
  readonly manifest_file?: ExportFileRecord;
  readonly package_file?: ExportFileRecord;
  readonly created_at: string;
  readonly expires_at: string;
  readonly error_code?: string;
}

export interface RenderedExportPayload {
  readonly bytes: Uint8Array;
  readonly mime_type: string;
  readonly width?: number;
  readonly height?: number;
  readonly page_count?: number;
  readonly metadata?: Readonly<Record<string, unknown>>;
}

export interface ExportSourcePort {
  resolveExactSnapshot(spec: ExportSpec): Promise<ExportSourceSnapshot>;
}

export interface ExportJobRepository {
  findByOperation(organizationId: string, operationId: string): Promise<ExportJob | null>;
  findReadyByFingerprint(organizationId: string, fingerprint: string, nowIso: string): Promise<ExportJob | null>;
  get(organizationId: string, exportJobId: string): Promise<ExportJob | null>;
  save(job: ExportJob): Promise<void>;
}

export interface ExportRendererPort {
  render(source: ExportSourceSnapshot, variant: ExportVariant): Promise<RenderedExportPayload>;
}

export interface ExportObjectStore {
  put(storageKey: string, payload: Uint8Array, mimeType: string): Promise<{
    readonly storage_key: string;
    readonly checksum_sha256: string;
    readonly size_bytes: number;
  }>;
  get(storageKey: string): Promise<Uint8Array>;
}

export interface ExportArtifactPort {
  persistExport(args: {
    readonly job: ExportJob;
    readonly files: readonly ExportFileRecord[];
    readonly manifest: ExportManifest;
    readonly package_file?: ExportFileRecord;
  }): Promise<void>;
}

export interface ExportAuthorizationPort {
  canDownload(args: {
    readonly organization_id: string;
    readonly project_id: string;
    readonly actor_id: string;
    readonly export_job_id: string;
    readonly file: ExportFileRecord;
  }): Promise<boolean>;
}

export interface ExportDownloadSignerPort {
  sign(args: {
    readonly storage_key: string;
    readonly filename: string;
    readonly expires_seconds: number;
  }): Promise<{ readonly url: string; readonly expires_at: string }>;
}

export interface ExportEventPort {
  emit(eventType: string, payload: Readonly<Record<string, unknown>>): Promise<void>;
}
