import { describe, expect, it } from "vitest";

import { assertPublicVersionProvenance } from "@/lib/versions/security";
import { branchHeadSnapshot, detectNewHead } from "@/lib/versions/state";
import {
  parseSafeVersionProvenance,
  parseVersionCompare,
  parseVersionHistory,
  semanticChanges,
} from "@/lib/versions/types";

const ID = "0198a1b2-c3d4-7e5f-8123-123456789abc";
const ID2 = "0198a1b2-c3d4-7e5f-8123-123456789abd";
const ID3 = "0198a1b2-c3d4-7e5f-8123-123456789abe";
const SHA = "1".repeat(64);
const GIT = "a".repeat(40);

function historyPayload(head = ID2): Record<string, unknown> {
  return {
    artifact: { id: ID, project_id: ID3, type: "DESIGN_DOCUMENT", name: "Poster", design_document_id: ID },
    branches: [{ id: ID3, artifact_id: ID, name: "main", base_version_id: ID, head_version_id: head, created_by_type: "USER", created_by_id: "u1", created_at: "2026-08-18T04:00:00Z" }],
    versions: [
      { id: ID, artifact_id: ID, branch_id: ID3, parent_version_id: null, version_number: 1, status: "APPROVED", content_hash: SHA, design_document_version_id: ID, quality_score: 0.9, constraint_snapshot_hash: SHA, created_by_type: "USER", created_by_id: "u1", created_at: "2026-08-18T04:00:00Z", preview: { mime_type: "application/json", width: null, height: null, duration_ms: null } },
      { id: ID2, artifact_id: ID, branch_id: ID3, parent_version_id: ID, version_number: 2, status: "DRAFT", content_hash: "2".repeat(64), design_document_version_id: ID2, quality_score: 0.8, constraint_snapshot_hash: SHA, created_by_type: "AGENT", created_by_id: "agent", created_at: "2026-08-18T04:05:00Z", preview: {} },
    ],
  };
}

describe("NODE-59 version contracts", () => {
  it("projects only canonical semantic diff categories", () => {
    const parsed = parseVersionCompare({
      left_version_id: ID,
      right_version_id: ID2,
      kind: "DESIGN_SEMANTIC",
      equal_content_hash: false,
      semantic_diff: {
        nodes_added: [ID3],
        nodes_removed: [],
        properties_changed: [`${ID}:opacity`],
        text_changed: [ID],
        geometry_changed: [ID2],
        asset_replaced: [],
        constraints_changed: [ID3],
        arbitrary_private_summary: "must not be projected",
      },
      visual_metrics: null,
      metadata: { ignored: true },
    });
    const changes = semanticChanges(parsed.semanticDiff);
    expect(changes.map((item) => item.category)).toEqual(["added", "property", "text", "geometry", "constraint"]);
    expect(changes.find((item) => item.category === "property")).toMatchObject({ subject: ID, property: "opacity" });
    expect(JSON.stringify(changes)).not.toContain("arbitrary_private_summary");
  });

  it("parses safe provenance without raw prompt references", () => {
    const payload = {
      artifact_version_id: ID,
      traceability_score: 1,
      traceability_status: "FULLY_TRACEABLE",
      missing_fields: [],
      agent_run_id: null,
      task_id: null,
      generation_id: null,
      provider: "openai",
      model: "gpt-image",
      prompt_hash: SHA,
      prompt_template_version: "v2",
      input_asset_ids: [],
      input_artifact_version_ids: [ID2],
      design_ir_schema_version: "1.0",
      constraint_snapshot_hash: SHA,
      recipe_version: "r4",
      skill_versions: [],
      code_git_sha: GIT,
      compiler_version: "1.2.0",
      agent_version: "agent-v3",
    };
    assertPublicVersionProvenance(payload);
    const value = parseSafeVersionProvenance(payload);
    expect(value.promptHash).toBe(SHA);
    expect(value.inputArtifactVersionIds).toEqual([ID2]);
    expect(value).not.toHaveProperty("promptRef");
    expect(value).not.toHaveProperty("providerRequestId");
  });

  it("rejects private provenance keys before projection", () => {
    expect(() => assertPublicVersionProvenance({ prompt_ref: "internal://private" })).toThrow("VERSION_PROVENANCE_PRIVATE_FIELD_FORBIDDEN");
    expect(() => assertPublicVersionProvenance({ nested: { provider_request_id: "secret-ref" } })).toThrow("VERSION_PROVENANCE_PRIVATE_FIELD_FORBIDDEN");
    expect(() => assertPublicVersionProvenance({ reasoning: "hidden" })).toThrow("VERSION_PROVENANCE_PRIVATE_FIELD_FORBIDDEN");
  });

  it("detects a concurrent new head without changing the viewed version", () => {
    const initial = parseVersionHistory(historyPayload(ID2));
    const baseline = branchHeadSnapshot(initial);
    const payload = historyPayload(ID3);
    const record = payload as { versions: unknown[] };
    record.versions.push({
      id: ID3,
      artifact_id: ID,
      branch_id: ID3,
      parent_version_id: ID2,
      version_number: 3,
      status: "DRAFT",
      content_hash: "3".repeat(64),
      design_document_version_id: ID3,
      quality_score: 0.7,
      constraint_snapshot_hash: SHA,
      created_by_type: "AGENT",
      created_by_id: "agent",
      created_at: "2026-08-18T04:10:00Z",
      preview: {},
    });
    const updated = parseVersionHistory(payload);
    expect(detectNewHead(updated, baseline, ID)).toBe(ID3);
    expect(ID).not.toBe(ID3);
  });
});
