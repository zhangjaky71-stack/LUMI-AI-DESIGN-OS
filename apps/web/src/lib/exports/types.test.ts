import { describe, expect, it } from "vitest";

import {
  parseExportCapabilities,
  parseExportDownloadGrant,
  parseExportJob,
} from "@/lib/exports/types";

const ID = "0198a1b2-c3d4-7e5f-8123-123456789abc";
const ID2 = "0198a1b2-c3d4-7e5f-8123-123456789abd";
const SHA = "a".repeat(64);

function capability(format = "PNG") {
  return {
    artifact_version_id: ID,
    approved: true,
    source_mime_type: "image/png",
    formats: [
      { format: "ORIGINAL", label: "Original file", output_extension: "png", copy_through: true },
      { format, label: format, output_extension: "png", copy_through: true },
    ],
    supports_resize: false,
    supports_quality: false,
    supports_alpha: false,
    supports_print_options: false,
    supports_ai_adapt: false,
    supports_batch_zip: true,
    max_batch_items: 500,
  };
}

describe("NODE-60 export contracts", () => {
  it("accepts only renderer-declared runtime formats and capability flags", () => {
    const value = parseExportCapabilities(capability());
    expect(value.formats.map((item) => item.format)).toEqual(["ORIGINAL", "PNG"]);
    expect(value.supportsResize).toBe(false);
    expect(value.supportsPrintOptions).toBe(false);
    expect(value.supportsAiAdapt).toBe(false);
  });

  it("rejects unimplemented WebP and SVG formats", () => {
    expect(() => parseExportCapabilities(capability("WEBP"))).toThrow("EXPORT_FORMAT_INVALID");
    expect(() => parseExportCapabilities(capability("SVG"))).toThrow("EXPORT_FORMAT_INVALID");
  });

  it("parses the actual Export Engine status enum", () => {
    for (const status of ["PLANNED", "QUEUED", "RENDERING", "PACKAGING", "READY", "FAILED", "CANCELLED", "EXPIRED"]) {
      const value = parseExportJob({
        job_id: ID,
        project_id: ID2,
        task_id: ID,
        operation_id: ID2,
        status,
        items: [{ artifact_version_id: ID, target_format: "PNG", output_name: "poster.png" }],
        outputs: [],
        package: null,
        manifest: null,
        error_code: null,
      });
      expect(value.status).toBe(status);
    }
    expect(() => parseExportJob({
      job_id: ID,
      project_id: ID2,
      task_id: ID,
      operation_id: ID2,
      status: "VALIDATING",
      items: [],
      outputs: [],
      package: null,
      manifest: null,
      error_code: null,
    })).toThrow("EXPORT_STATUS_INVALID");
  });

  it("preserves exact source version and checksums in the public manifest", () => {
    const value = parseExportJob({
      job_id: ID,
      project_id: ID2,
      task_id: ID,
      operation_id: ID2,
      status: "READY",
      items: [{ artifact_version_id: ID, target_format: "ORIGINAL", output_name: "poster.png" }],
      outputs: [{
        name: "poster.png",
        mime_type: "image/png",
        size_bytes: 100,
        checksum_sha256: SHA,
        renderer_version: "copy-through/1.0",
        source_artifact_id: ID2,
        source_artifact_version_id: ID,
        bucket: "must-not-be-projected",
        storage_key: "must-not-be-projected",
      }],
      package: {
        package_id: ID2,
        filename: "poster.png",
        mime_type: "image/png",
        size_bytes: 100,
        checksum_sha256: SHA,
        is_archive: false,
      },
      manifest: {
        schema_version: "1",
        export_job_id: ID,
        operation_id: ID2,
        created_at: "2026-08-18T04:00:00Z",
        exporter_version: "export-engine/1.0",
        entries: [{
          name: "poster.png",
          mime_type: "image/png",
          size_bytes: 100,
          checksum_sha256: SHA,
          artifact_id: ID2,
          artifact_version_id: ID,
          renderer_version: "copy-through/1.0",
          storage_key: "must-not-be-projected",
        }],
      },
      error_code: null,
    });
    expect(value.outputs[0]).not.toHaveProperty("bucket");
    expect(value.outputs[0]).not.toHaveProperty("storageKey");
    expect(value.manifest?.entries[0]?.artifactVersionId).toBe(ID);
    expect(value.manifest?.entries[0]?.checksumSha256).toBe(SHA);
  });

  it("parses a re-signed download grant without persisting URL into the job contract", () => {
    const value = parseExportDownloadGrant({
      job_id: ID,
      package_id: ID2,
      filename: "poster.png",
      mime_type: "image/png",
      size_bytes: 100,
      checksum_sha256: SHA,
      expires_at: "2026-08-18T04:15:00Z",
      url: "https://signed.example.test/object?sig=temporary",
    });
    expect(value.url).toContain("sig=temporary");
    expect(value.expiresAt).toBe("2026-08-18T04:15:00Z");
  });
});
