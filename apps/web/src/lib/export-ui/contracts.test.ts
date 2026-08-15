import { describe, expect, it } from "vitest";
import {
  buildExportSpec,
  capabilitiesForSource,
  hasAspectRatioChange,
  safeExportError,
  safeFilename,
  VERIFIED_EXPORT_CAPABILITIES,
} from "./contracts";
import type { ExportDraft, ExportSourceOption } from "./types";

const source: ExportSourceOption = {
  id: "source-1", label: "Exact", entry_kind: "FRAME", artifact_id: "artifact-1",
  artifact_version_id: "artifact-v4", design_document_version_id: "design-v9", frame_ids: ["frame-1"],
  width: 1080, height: 1350, supports_vector: true, approved: true, brand_rule_set_version: "brand-v2",
};

function draft(overrides: Partial<ExportDraft> = {}): ExportDraft {
  return { source, format: "PNG", size_mode: "ORIGINAL", target_width: 1080, target_height: 1350, resize_mode: "SCALE", quality: null, transparent_background: false, include_manifest: true, filename: "Summer Launch", ...overrides };
}

describe("NODE-60 export contracts", () => {
  it("pins exact ArtifactVersion and DesignVersion", () => {
    const spec = buildExportSpec({ organizationId: "org-1", projectId: "project-1", actorId: "user-1", operationId: "op-1", draft: draft() });
    expect(spec.artifact_version_id).toBe("artifact-v4");
    expect(spec.design_document_version_id).toBe("design-v9");
    expect(spec.variants[0]?.resize_mode).toBe("SCALE");
  });

  it("rejects floating version aliases", () => {
    expect(() => buildExportSpec({ organizationId: "org-1", projectId: "project-1", actorId: "user-1", operationId: "op-1", draft: draft({ source: { ...source, artifact_version_id: "latest" } }) })).toThrow(/MUST_BE_EXACT/);
  });

  it("hides SVG for raster source and ZIP for single frame", () => {
    const caps = capabilitiesForSource({ ...source, supports_vector: false }, VERIFIED_EXPORT_CAPABILITIES);
    expect(caps.some((item) => item.format === "SVG")).toBe(false);
    expect(caps.some((item) => item.format === "ZIP")).toBe(false);
  });

  it("only exposes multi-frame formats for batch source", () => {
    const caps = capabilitiesForSource({ ...source, frame_ids: ["a", "b"] }, VERIFIED_EXPORT_CAPABILITIES);
    expect(caps.map((item) => item.format)).toEqual(["PDF", "ZIP", "LUMI_PACKAGE"]);
  });

  it("detects aspect ratio changes without inventing AI adaptation", () => {
    expect(hasAspectRatioChange(source, 1080, 1080)).toBe(true);
    expect(hasAspectRatioChange(source, 2160, 2700)).toBe(false);
  });

  it("rejects JPEG alpha", () => {
    expect(() => buildExportSpec({ organizationId: "org-1", projectId: "project-1", actorId: "user-1", operationId: "op-1", draft: draft({ format: "JPEG", transparent_background: true, quality: 90 }) })).toThrow("EXPORT_JPEG_ALPHA_UNSUPPORTED");
  });

  it("normalizes unsafe filenames", () => {
    expect(safeFilename("  Summer / Launch ..  ")).toBe("Summer-Launch-..");
  });

  it("shows opaque request IDs without exposing raw payloads", () => {
    expect(safeExportError("EXPORT_DOWNLOAD_FORBIDDEN::request:req-1234")).toBe("Download permission changed. Ask a project owner for access. Request ID: req-1234");
  });
});
