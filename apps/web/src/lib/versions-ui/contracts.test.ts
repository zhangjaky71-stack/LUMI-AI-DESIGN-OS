import { describe, expect, it } from "vitest";
import { normalizeBranchName, safeProvenance, validateForkInput } from "./contracts";
import type { VersionTimelineItem } from "./types";

const item: VersionTimelineItem = {
  version: {
    id: "version-1",
    organization_id: "org-lumi",
    artifact_id: "artifact-1",
    branch_id: "branch-1",
    parent_version_id: null,
    schema_version: "design-ir@1",
    version_number: 1,
    status: "READY",
    content_hash: "a".repeat(64),
    constraint_snapshot_hash: "0".repeat(64),
    created_by_type: "AGENT",
    created_by_id: "agent:designer",
    created_at: "2026-08-15T01:00:00.000Z",
    brand_rule_set_version: "1.0.0",
    quality_score: 91,
  },
  branch_name: "main",
  semantic_changes: [],
  preview: {
    kind: "DESIGN_IR",
    label: "preview",
    width: 1080,
    height: 1350,
    background: "#FFFFFF",
    accent: "#111111",
    secondary: "#777777",
    image_asset_id: null,
  },
  approval: {
    status: "READY",
    approved_by: null,
    approved_at: null,
    validation_label: null,
  },
  quality: { score: 91, label: "Ready", checks: ["Brand compliance"] },
  safe_change_summary: "Structured semantic summary",
  lineage_labels: [],
};

describe("Versions UI contracts", () => {
  it("normalizes a human branch name without creating an implicit merge", () => {
    expect(normalizeBranchName("  Dark Direction  ")).toBe("dark-direction");
    expect(validateForkInput({ artifact_id: "a", source_version_id: "v1", name: "Dark Direction" }).name).toBe("dark-direction");
  });

  it("rejects branch names outside the bounded product contract", () => {
    expect(() => validateForkInput({ artifact_id: "a", source_version_id: "v1", name: "x" })).toThrow();
    expect(() => validateForkInput({ artifact_id: "a", source_version_id: "v1", name: "../../main" })).toThrow();
  });

  it("projects safe provenance hashes instead of raw prompts or private reasoning", () => {
    const projected = safeProvenance(item, {
      model: "model-router",
      provider: "provider-a",
      agent_run_id: "run-1",
      prompt_hash: "b".repeat(64),
      prompt_template_version: "visual@3",
      constraint_snapshot_hash: "0".repeat(64),
      code_git_sha: "abc123",
    });
    const serialized = JSON.stringify(projected);
    expect(projected.prompt_hash).toBe("b".repeat(64));
    expect(projected.brand_rule_set_version).toBe("1.0.0");
    expect(serialized).not.toContain("raw_prompt");
    expect(serialized).not.toContain("system_prompt");
    expect(serialized).not.toContain("chain_of_thought");
    expect(serialized).not.toContain("tool_payload");
  });
});
