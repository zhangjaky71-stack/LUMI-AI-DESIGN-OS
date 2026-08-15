import type {
  ExportFormat,
  ExportJobStatus,
  ExportResizeMode,
  ExportSpec,
} from "@lumi/artifact-sdk";

export type ExportEntryKind = "FRAME" | "ARTIFACT_VERSION" | "DELIVERABLE" | "BATCH";

export interface ExportSourceOption {
  readonly id: string;
  readonly label: string;
  readonly entry_kind: ExportEntryKind;
  readonly artifact_id: string;
  readonly artifact_version_id: string;
  readonly design_document_version_id: string;
  readonly frame_ids: readonly string[];
  readonly width: number;
  readonly height: number;
  readonly supports_vector: boolean;
  readonly approved: boolean;
  readonly brand_rule_set_version: string | null;
}

export interface ExportCapability {
  readonly format: ExportFormat;
  readonly label: string;
  readonly supports_quality: boolean;
  readonly supports_alpha: boolean;
  readonly supports_multi_frame: boolean;
  readonly package_format: boolean;
}

export interface ExportHistoryItem {
  readonly export_job_id: string;
  readonly artifact_version_id: string;
  readonly design_document_version_id: string;
  readonly status: ExportJobStatus;
  readonly created_at: string;
  readonly files: readonly ExportFileView[];
  readonly manifest_available: boolean;
  readonly error_code?: string;
}

export interface ExportFileView {
  readonly file_id: string;
  readonly filename: string;
  readonly mime_type: string;
  readonly checksum_sha256: string;
  readonly size_bytes: number;
}

export interface ExportWorkspaceSnapshot {
  readonly organization_id: string;
  readonly project_id: string;
  readonly actor_id: string;
  readonly sources: readonly ExportSourceOption[];
  readonly active_source_id: string | null;
  readonly capabilities: readonly ExportCapability[];
  readonly history: readonly ExportHistoryItem[];
  readonly partial_retry_supported: boolean;
  readonly export_engine_version: string;
}

export interface ExportBootstrap {
  readonly mode: "HTTP" | "DETERMINISTIC";
  readonly organization_id: string;
  readonly project_id: string;
  readonly actor_id: string;
  readonly workspace: ExportWorkspaceSnapshot | null;
}

export interface ExportDraft {
  readonly source: ExportSourceOption;
  readonly format: ExportFormat;
  readonly size_mode: "ORIGINAL" | "2X" | "CUSTOM" | "PRESET";
  readonly target_width: number;
  readonly target_height: number;
  readonly resize_mode: ExportResizeMode;
  readonly quality: number | null;
  readonly transparent_background: boolean;
  readonly include_manifest: boolean;
  readonly filename: string;
}

export interface ExportJobView {
  readonly export_job_id: string;
  readonly status: ExportJobStatus;
  readonly progress: number;
  readonly artifact_version_id: string;
  readonly design_document_version_id: string;
  readonly export_fingerprint: string;
  readonly files: readonly ExportFileView[];
  readonly error_code?: string;
}

export interface ExportDownloadLease {
  readonly url: string;
  readonly expires_at: string;
  readonly filename: string;
}

export interface ExportEstimate {
  readonly ai_generation_cost: number;
  readonly render_label: string;
  readonly note: string;
}

export interface SafeExportProblem extends Error {
  readonly code: string;
  readonly status: number;
  readonly request_id: string | null;
}

export interface CreateExportInput {
  readonly spec: ExportSpec;
}
