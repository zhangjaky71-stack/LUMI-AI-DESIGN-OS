import { canonicalEngineLabel, VERIFIED_EXPORT_CAPABILITIES } from "./contracts";
import type { ExportBootstrap, ExportWorkspaceSnapshot } from "./types";

function deterministicEnabled(): boolean {
  return process.env.NODE_ENV !== "production" && process.env.LUMI_EXPORT_UI_E2E === "1";
}

function deterministicWorkspace(projectId: string): ExportWorkspaceSnapshot {
  return {
    organization_id: "org-lumi-e2e",
    project_id: projectId,
    actor_id: "user-owner-e2e",
    export_engine_version: canonicalEngineLabel(),
    partial_retry_supported: false,
    capabilities: VERIFIED_EXPORT_CAPABILITIES,
    active_source_id: "source-design-v4",
    sources: [
      {
        id: "source-design-v4",
        label: "Summer Launch · Design v4 · Frame 01",
        entry_kind: "FRAME",
        artifact_id: "artifact-summer-launch-design",
        artifact_version_id: "artifact-summer-launch-design-v4",
        design_document_version_id: "design-summer-launch-v4",
        frame_ids: ["frame-hero"],
        width: 1080,
        height: 1350,
        supports_vector: true,
        approved: true,
        brand_rule_set_version: "brand-summer-v2",
      },
      {
        id: "source-batch-v4",
        label: "Summer Launch · Deliverables · 4 frames",
        entry_kind: "BATCH",
        artifact_id: "artifact-summer-launch-design",
        artifact_version_id: "artifact-summer-launch-design-v4",
        design_document_version_id: "design-summer-launch-v4",
        frame_ids: ["frame-hero", "frame-story", "frame-square", "frame-banner"],
        width: 1080,
        height: 1350,
        supports_vector: true,
        approved: true,
        brand_rule_set_version: "brand-summer-v2",
      },
      {
        id: "source-raster-v3",
        label: "Campaign Photo · ArtifactVersion v3",
        entry_kind: "ARTIFACT_VERSION",
        artifact_id: "artifact-campaign-photo",
        artifact_version_id: "artifact-campaign-photo-v3",
        design_document_version_id: "design-campaign-photo-v3",
        frame_ids: ["frame-photo"],
        width: 2048,
        height: 2048,
        supports_vector: false,
        approved: true,
        brand_rule_set_version: null,
      },
    ],
    history: [
      {
        export_job_id: "export-e2e-ready-file",
        artifact_version_id: "artifact-summer-launch-design-v4",
        design_document_version_id: "design-summer-launch-v4",
        status: "READY",
        created_at: "2026-08-15T04:20:00.000Z",
        manifest_available: true,
        files: [{
          file_id: "export-e2e-ready-file-png",
          filename: "summer-launch-approved.png",
          mime_type: "image/png",
          checksum_sha256: "3d3f0a49b61136d4c78fdd4d6ebaa8a9a382daaf96f68ecba079eaf8ad521e28",
          size_bytes: 388120,
        }],
      },
      {
        export_job_id: "export-e2e-partial-boundary",
        artifact_version_id: "artifact-summer-launch-design-v4",
        design_document_version_id: "design-summer-launch-v4",
        status: "FAILED",
        created_at: "2026-08-15T04:00:00.000Z",
        manifest_available: false,
        files: [],
        error_code: "EXPORT_BATCH_ITEM_FAILED",
      },
    ],
  };
}

export function getExportBootstrap(projectId: string): ExportBootstrap {
  if (deterministicEnabled()) {
    const workspace = deterministicWorkspace(projectId);
    return {
      mode: "DETERMINISTIC",
      organization_id: workspace.organization_id,
      project_id: projectId,
      actor_id: workspace.actor_id,
      workspace,
    };
  }
  return {
    mode: "HTTP",
    organization_id: "",
    project_id: projectId,
    actor_id: "",
    workspace: null,
  };
}
