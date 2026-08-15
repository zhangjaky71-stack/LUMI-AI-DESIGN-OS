import { describe, expect, it } from "vitest";
import { DeterministicExportGateway } from "./export-gateway";
import { VERIFIED_EXPORT_CAPABILITIES } from "./contracts";
import type { ExportSpec } from "@lumi/artifact-sdk";
import type { ExportWorkspaceSnapshot } from "./types";

const workspace: ExportWorkspaceSnapshot = {
  organization_id: "org-1", project_id: "project-1", actor_id: "user-1", export_engine_version: "NODE-49",
  partial_retry_supported: false, capabilities: VERIFIED_EXPORT_CAPABILITIES, active_source_id: "source-1", history: [],
  sources: [{ id: "source-1", label: "source", entry_kind: "FRAME", artifact_id: "artifact-1", artifact_version_id: "artifact-v4", design_document_version_id: "design-v4", frame_ids: ["frame-1"], width: 1080, height: 1350, supports_vector: true, approved: true, brand_rule_set_version: null }],
};
const spec: ExportSpec = { organization_id: "org-1", project_id: "project-1", requested_by: "user-1", operation_id: "op-1", artifact_version_id: "artifact-v4", design_document_version_id: "design-v4", variants: [{ variant_id: "primary", frame_ids: ["frame-1"], format: "PNG", width: 1080, height: 1350, resize_mode: "SCALE", color_profile: "SRGB", unit: "PX" }], filename_template: "x-{variant}.{ext}", include_manifest: true, retention_seconds: 3600 };

describe("Deterministic NODE-60 gateway", () => {
  it("advances only through canonical job states and then exposes READY file", async () => {
    const gateway = new DeterministicExportGateway(workspace);
    let job = await gateway.createExport(spec);
    expect(job.status).toBe("PENDING");
    for (let index = 0; index < 4; index += 1) job = await gateway.getExport(job.export_job_id);
    expect(job.status).toBe("READY");
    expect(job.files).toHaveLength(1);
  });

  it("refreshes a signed URL without rerendering", async () => {
    const gateway = new DeterministicExportGateway(workspace);
    let job = await gateway.createExport(spec);
    for (let index = 0; index < 4; index += 1) job = await gateway.getExport(job.export_job_id);
    const first = await gateway.getDownload(job.export_job_id, job.files[0]!.file_id);
    const second = await gateway.getDownload(job.export_job_id, job.files[0]!.file_id);
    expect(first.url).not.toBe(second.url);
    expect((await gateway.getExport(job.export_job_id)).status).toBe("READY");
  });

  it("rejects floating exact-version aliases", async () => {
    const gateway = new DeterministicExportGateway(workspace);
    await expect(gateway.createExport({ ...spec, artifact_version_id: "latest", operation_id: "op-2" })).rejects.toThrow("EXPORT_VERSION_MUST_BE_EXACT");
  });
});
