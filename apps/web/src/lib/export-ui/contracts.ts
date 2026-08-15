import {
  EXPORT_ENGINE_VERSION,
  type ExportFormat,
  type ExportSpec,
} from "@lumi/artifact-sdk";
import type {
  ExportCapability,
  ExportDraft,
  ExportEstimate,
  ExportSourceOption,
  SafeExportProblem,
} from "./types";

const FLOATING_VERSION = /^(latest|head|current)$/i;
const SAFE_FILENAME = /[^a-zA-Z0-9._-]+/g;

export const VERIFIED_EXPORT_CAPABILITIES: readonly ExportCapability[] = [
  { format: "PNG", label: "PNG", supports_quality: false, supports_alpha: true, supports_multi_frame: false, package_format: false },
  { format: "JPEG", label: "JPEG", supports_quality: true, supports_alpha: false, supports_multi_frame: false, package_format: false },
  { format: "WEBP", label: "WebP", supports_quality: true, supports_alpha: true, supports_multi_frame: false, package_format: false },
  { format: "SVG", label: "SVG", supports_quality: false, supports_alpha: true, supports_multi_frame: false, package_format: false },
  { format: "PDF", label: "PDF", supports_quality: false, supports_alpha: false, supports_multi_frame: true, package_format: false },
  { format: "ZIP", label: "ZIP Batch", supports_quality: false, supports_alpha: false, supports_multi_frame: true, package_format: true },
  { format: "LUMI_PACKAGE", label: "LUMI Project Package", supports_quality: false, supports_alpha: false, supports_multi_frame: true, package_format: true },
] as const;

export function exportProblem(code: string, status = 400, requestId: string | null = null): SafeExportProblem {
  const error = new Error(code) as SafeExportProblem;
  Object.assign(error, { code, status, request_id: requestId });
  return error;
}

export function assertExactVersionId(value: string, field: string): void {
  if (!value.trim() || FLOATING_VERSION.test(value.trim())) throw exportProblem(`EXPORT_${field.toUpperCase()}_MUST_BE_EXACT`);
}

export function capabilitiesForSource(
  source: ExportSourceOption,
  capabilities: readonly ExportCapability[],
): readonly ExportCapability[] {
  return capabilities.filter((capability) => {
    if (capability.format === "SVG" && !source.supports_vector) return false;
    if (source.frame_ids.length > 1 && !capability.supports_multi_frame) return false;
    if (capability.format === "ZIP" && source.frame_ids.length < 2) return false;
    return true;
  });
}

export function hasAspectRatioChange(source: ExportSourceOption, width: number, height: number): boolean {
  if (width <= 0 || height <= 0) return false;
  return Math.abs(source.width / source.height - width / height) > 0.001;
}

export function safeFilename(value: string, fallback = "lumi-export"): string {
  const normalized = value.trim().replace(SAFE_FILENAME, "-").replace(/^-+|-+$/g, "").slice(0, 120);
  return normalized || fallback;
}

export function estimateExport(source: ExportSourceOption, format: ExportFormat): ExportEstimate {
  const batch = source.frame_ids.length > 1;
  return {
    ai_generation_cost: 0,
    render_label: batch || format === "PDF" || format === "ZIP" ? "Server render / packaging" : "Server render",
    note: "Export itself has no AI generation charge. AI Adapt is a separate version-producing workflow and is estimated there.",
  };
}

export function buildExportSpec(args: {
  organizationId: string;
  projectId: string;
  actorId: string;
  operationId: string;
  draft: ExportDraft;
}): ExportSpec {
  const { draft } = args;
  assertExactVersionId(draft.source.artifact_version_id, "artifact_version_id");
  assertExactVersionId(draft.source.design_document_version_id, "design_version_id");
  if (draft.target_width <= 0 || draft.target_height <= 0) throw exportProblem("EXPORT_DIMENSIONS_INVALID");
  if (draft.format === "JPEG" && draft.transparent_background) throw exportProblem("EXPORT_JPEG_ALPHA_UNSUPPORTED");
  if (draft.quality !== null && (draft.quality < 1 || draft.quality > 100)) throw exportProblem("EXPORT_QUALITY_INVALID");

  return {
    organization_id: args.organizationId,
    project_id: args.projectId,
    requested_by: args.actorId,
    operation_id: args.operationId,
    artifact_version_id: draft.source.artifact_version_id,
    design_document_version_id: draft.source.design_document_version_id,
    variants: [{
      variant_id: "primary",
      frame_ids: draft.source.frame_ids,
      format: draft.format,
      width: draft.target_width,
      height: draft.target_height,
      resize_mode: draft.resize_mode,
      ...(draft.quality === null ? {} : { quality: draft.quality }),
      ...(draft.format === "PNG" || draft.format === "WEBP" ? { transparent_background: draft.transparent_background } : {}),
      color_profile: "SRGB",
      unit: "PX",
      dpi: 96,
      filename: safeFilename(draft.filename),
    }],
    filename_template: `${safeFilename(draft.filename)}-{variant}.{ext}`,
    include_manifest: draft.include_manifest,
    retention_seconds: 60 * 60 * 24 * 7,
  };
}

export function statusLabel(status: string): string {
  switch (status) {
    case "PENDING": return "Preparing";
    case "RENDERING": return "Rendering";
    case "PACKAGING": return "Packaging";
    case "VALIDATING": return "Validating";
    case "READY": return "Ready";
    case "FAILED": return "Failed";
    case "EXPIRED": return "Expired";
    default: return "Unknown";
  }
}

export function safeExportError(code: string | undefined): string {
  const [safeCode, requestId] = (code ?? "").split("::request:", 2);
  let message: string;
  switch (safeCode) {
    case "EXPORT_EXACT_SOURCE_NOT_FOUND": message = "The exact source version is no longer available to this request."; break;
    case "EXPORT_DOWNLOAD_FORBIDDEN": message = "Download permission changed. Ask a project owner for access."; break;
    case "EXPORT_JOB_EXPIRED": message = "This export expired. Create a new export from the same exact source version."; break;
    case "EXPORT_STORAGE_OBJECT_NOT_FOUND": message = "The verified export file is unavailable in storage."; break;
    case "EXPORT_VIDEO_NODE_REQUIRES_NODE_48": message = "This selection contains video. Use the video export workflow."; break;
    default: message = "Export could not be completed without exposing internal details.";
  }
  return requestId ? `${message} Request ID: ${requestId}` : message;
}

export function canonicalEngineLabel(): string {
  return `NODE-49 Export Engine v${EXPORT_ENGINE_VERSION}`;
}
