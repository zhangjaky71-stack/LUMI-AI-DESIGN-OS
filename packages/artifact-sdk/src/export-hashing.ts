import { canonicalSha256, canonicalStringify } from "../../design-ir/src/index";
import type {
  ExportFileRecord,
  ExportManifest,
  ExportManifestFile,
  ExportSourceSnapshot,
  ExportSpec,
} from "./export-engine-types";
import { assertNoEphemeralExportRefs, assertNoSensitiveExportMetadata } from "./export-security";

function semanticSpec(spec: ExportSpec): unknown {
  return {
    organization_id: spec.organization_id,
    project_id: spec.project_id,
    artifact_version_id: spec.artifact_version_id,
    design_document_version_id: spec.design_document_version_id,
    filename_template: spec.filename_template,
    include_manifest: spec.include_manifest,
    variants: [...spec.variants]
      .map((variant) => ({
        variant_id: variant.variant_id,
        frame_ids: [...variant.frame_ids],
        format: variant.format,
        width: variant.width ?? null,
        height: variant.height ?? null,
        scale: variant.scale ?? null,
        resize_mode: variant.resize_mode ?? "SCALE",
        quality: variant.quality ?? null,
        transparent_background: variant.transparent_background ?? false,
        background: variant.background ?? null,
        color_profile: variant.color_profile ?? "SRGB",
        dpi: variant.dpi ?? 72,
        unit: variant.unit ?? "PX",
        bleed: variant.bleed ?? 0,
        crop_marks: variant.crop_marks ?? false,
        filename: variant.filename ?? null,
      }))
      .sort((a, b) => a.variant_id.localeCompare(b.variant_id)),
  };
}

export async function exportFingerprint(source: ExportSourceSnapshot, spec: ExportSpec): Promise<string> {
  if (source.artifact_version_id !== spec.artifact_version_id) {
    throw new Error("EXPORT_SOURCE_ARTIFACT_VERSION_MISMATCH");
  }
  if (source.design_document_version_id !== spec.design_document_version_id) {
    throw new Error("EXPORT_SOURCE_DESIGN_VERSION_MISMATCH");
  }
  assertNoSensitiveExportMetadata(source.design_document, "$.design_document");
  assertNoSensitiveExportMetadata(source.rights_summary, "$.rights_summary");
  if (source.project_snapshot) assertNoSensitiveExportMetadata(source.project_snapshot, "$.project_snapshot");
  assertNoEphemeralExportRefs(source.design_document, "$.design_document");
  assertNoEphemeralExportRefs(source.render_plan, "$.render_plan");
  return canonicalSha256({
    export_engine: "1.0.0",
    source: {
      artifact_id: source.artifact_id,
      artifact_version_id: source.artifact_version_id,
      design_document_version_id: source.design_document_version_id,
      content_hash: source.content_hash,
      constraint_snapshot_hash: source.constraint_snapshot_hash,
      compiler: source.compiler_provenance,
    },
    spec: semanticSpec(spec),
  });
}

export async function exportManifestHash(
  manifest: Omit<ExportManifest, "manifest_sha256">,
): Promise<string> {
  assertNoSensitiveExportMetadata(manifest, "$.manifest");
  return canonicalSha256(manifest);
}

export function canonicalExportJson(value: unknown): string {
  return canonicalStringify(value);
}

export function stableExportFiles(files: readonly ExportFileRecord[]): readonly ExportManifestFile[] {
  return [...files]
    .sort((a, b) => a.filename.localeCompare(b.filename))
    .map((file) => ({
      filename: file.filename,
      mime_type: file.mime_type,
      checksum_sha256: file.checksum_sha256,
      size_bytes: file.size_bytes,
      ...(file.width !== undefined ? { width: file.width } : {}),
      ...(file.height !== undefined ? { height: file.height } : {}),
      ...(file.page_count !== undefined ? { page_count: file.page_count } : {}),
    }));
}
