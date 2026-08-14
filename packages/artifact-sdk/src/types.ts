export const ARTIFACT_ENGINE_VERSION = "1.0.0";

export type ArtifactType =
  | "DESIGN_DOCUMENT"
  | "RASTER_IMAGE"
  | "VECTOR_IMAGE"
  | "VIDEO"
  | "AUDIO"
  | "PDF"
  | "HTML"
  | "ARCHIVE"
  | "EXPORT_PACKAGE";

export type ArtifactVersionStatus = "DRAFT" | "READY" | "APPROVED" | "REJECTED" | "ARCHIVED";
export type ArtifactLineageType =
  | "DERIVED_FROM"
  | "EDITED_FROM"
  | "GENERATED_FROM"
  | "COMPOSED_FROM"
  | "RESIZED_FROM"
  | "EXPORTED_FROM"
  | "REFERENCE_USED";
export type ArtifactFileRole =
  | "PREVIEW"
  | "ORIGINAL"
  | "THUMBNAIL"
  | "WEB_OPTIMIZED"
  | "PRINT_PDF"
  | "LAYER_DATA";
export type ArtifactExportFormat = "PNG" | "JPEG" | "WEBP" | "PDF" | "SVG";

export interface Artifact {
  readonly id: string;
  readonly organization_id: string;
  readonly project_id: string;
  readonly type: ArtifactType;
  readonly title: string;
  readonly archived: boolean;
}

export interface ArtifactBranch {
  readonly id: string;
  readonly organization_id: string;
  readonly artifact_id: string;
  readonly name: string;
  readonly base_version_id: string | null;
  readonly head_version_id: string | null;
  readonly created_by: string;
}

export interface ArtifactVersion {
  readonly id: string;
  readonly organization_id: string;
  readonly artifact_id: string;
  readonly branch_id: string;
  readonly parent_version_id: string | null;
  readonly schema_version: string;
  readonly version_number: number;
  readonly status: ArtifactVersionStatus;
  readonly content_hash: string;
  readonly constraint_snapshot_hash: string;
  readonly created_by_type: "USER" | "AGENT" | "SYSTEM";
  readonly created_by_id: string;
  readonly created_at: string;
  readonly primary_file_id?: string | null;
  readonly design_document_version_id?: string | null;
  readonly brand_rule_set_version?: string | null;
  readonly identity_validation_snapshot_id?: string | null;
  readonly quality_score?: number | null;
}

export interface ArtifactFile {
  readonly id: string;
  readonly organization_id: string;
  readonly artifact_version_id: string;
  readonly role: ArtifactFileRole;
  readonly storage_key: string;
  readonly mime_type: string;
  readonly size_bytes: number;
  readonly checksum_sha256: string;
  readonly width?: number;
  readonly height?: number;
  readonly duration_ms?: number;
  readonly metadata?: Readonly<Record<string, unknown>>;
}

export interface ArtifactLineageEdge {
  readonly id: string;
  readonly organization_id: string;
  readonly from_version_id: string;
  readonly to_version_id: string;
  readonly type: ArtifactLineageType;
  readonly metadata?: Readonly<Record<string, unknown>>;
}

export interface CompilerArtifactProvenance {
  readonly compiler_version: string;
  readonly document_id: string;
  readonly schema_version: string;
  readonly document_version: number;
  readonly resource_versions: Readonly<Record<string, string>>;
  readonly font_versions: Readonly<Record<string, string>>;
  readonly compile_hash: string;
}

export interface ArtifactProvenance {
  readonly artifact_version_id: string;
  readonly organization_id: string;
  readonly constraint_snapshot_hash: string;
  readonly code_git_sha: string;
  readonly compiler?: CompilerArtifactProvenance;
  readonly brand_rule_set_version?: string;
  readonly identity_validation_snapshot_id?: string;
  readonly agent_run_id?: string;
  readonly task_id?: string;
  readonly generation_id?: string;
  readonly provider?: string;
  readonly model?: string;
  readonly provider_request_id?: string;
  readonly prompt_hash?: string;
  readonly prompt_template_version?: string;
  readonly input_asset_ids?: readonly string[];
  readonly input_artifact_version_ids?: readonly string[];
  readonly design_ir_schema_version?: string;
  readonly recipe_version?: string;
  readonly skill_versions?: Readonly<Record<string, string>>;
}

export interface StoredObjectStat {
  readonly storage_key: string;
  readonly size_bytes: number;
  readonly checksum_sha256: string;
  readonly mime_type?: string;
}

export interface ArtifactObjectStore {
  stat(storageKey: string): Promise<StoredObjectStat | null>;
  delete?(storageKey: string): Promise<void>;
}

export interface ArtifactExportRequest {
  readonly artifact_version_id: string;
  readonly format: ArtifactExportFormat;
  readonly render_plan: unknown;
  readonly compiler_provenance: CompilerArtifactProvenance;
  readonly options?: Readonly<Record<string, unknown>>;
}

export interface ArtifactExportPayload {
  readonly bytes: Uint8Array;
  readonly mime_type: string;
  readonly width?: number;
  readonly height?: number;
}

export interface ArtifactExportAdapter {
  readonly format: ArtifactExportFormat;
  render(request: ArtifactExportRequest): Promise<ArtifactExportPayload>;
}
