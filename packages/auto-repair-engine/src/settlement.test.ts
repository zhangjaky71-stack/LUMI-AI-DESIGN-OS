import { describe, expect, it } from "vitest";
import type { DesignDocument } from "../../design-ir/src/index";
import type { QualityResult } from "../../quality-engine/src/index";
import { MemoryRepairArtifactRepository, MemoryRepairAttemptRepository } from "./memory-repository";
import { AutoRepairLoop } from "./runtime";
import type { RepairSource } from "./types";

const ORG = "00000000-0000-4000-8000-000000000001";
const PROJECT = "00000000-0000-4000-8000-000000000002";
const ARTIFACT = "00000000-0000-4000-8000-000000000003";
const VERSION = "00000000-0000-4000-8000-000000000004";
const BRANCH = "00000000-0000-4000-8000-000000000006";

const document: DesignDocument = {
  schema_version: "1.0",
  document_id: "settlement-doc",
  unit: "px",
  root_id: "root",
  nodes: { root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: [] } },
  resources: {},
  metadata: { document_version: 1 },
};

const quality: QualityResult = {
  quality_result_id: "quality-result:settlement-source",
  organization_id: ORG,
  project_id: PROJECT,
  artifact_id: ARTIFACT,
  artifact_version_id: VERSION,
  design_document_version_id: "00000000-0000-4000-8000-000000000005",
  profile_id: "quality:production-web",
  profile_version: "1.0.0",
  status: "FAIL_REPAIRABLE",
  overall_score: 50,
  confidence: 1,
  dimensions: [],
  violations: [{ violation_id: "v:image", dimension: "IMAGE_DEFECTS", severity: "MAJOR", reason_code: "BACKGROUND_NOISE", message: "noise", evidence_ids: [], repairable: true }],
  strengths: [],
  repair_actions: [],
  evidence: [],
  unavailable_graders: [],
  grader_versions: {},
  created_at: "2026-08-15T00:00:00Z",
};

const source: RepairSource = {
  branch_id: BRANCH,
  expected_branch_head: VERSION,
  subject: { organization_id: ORG, project_id: PROJECT, artifact_id: ARTIFACT, artifact_version_id: VERSION, design_document_version_id: quality.design_document_version_id, design_document: document, rendered_asset_ref: "source" },
  quality,
  constraints: [],
};

describe("NODE-51 paid settlement uncertainty", () => {
  it("does not release a reservation after the paid side effect has completed", async () => {
    const events: string[] = [];
    const repo = new MemoryRepairArtifactRepository(BRANCH, VERSION);
    const result = await new AutoRepairLoop({
      artifacts: repo,
      attempts: new MemoryRepairAttemptRepository(events),
      structural_materializer: { async materialize() { throw new Error("unused"); } },
      quality: { async evaluate() { throw new Error("quality must not run when settlement is uncertain"); } },
      cost_estimator: { async estimate() { return "0.4"; } },
      budget: {
        async remaining() { return "1"; },
        async reserve() { events.push("reserve"); return { reservation_id: "reservation:1", amount_usd: "0.4" }; },
        async settle() { events.push("settle"); throw new Error("ledger timeout"); },
        async release() { events.push("release"); },
      },
      generative: {
        async execute() {
          events.push("generate");
          return { design_document: document, rendered_asset_ref: "generated", content_hash: "a".repeat(64), constraint_snapshot_hash: "b".repeat(64), actual_cost_usd: "0.37" };
        },
      },
    }, { policy: { policy_id: "repair-policy:test", version: "1", max_auto_repair_iterations: 2, max_repair_cost_usd: "1", minimum_expected_gain: 5, max_score_regression: 2 } }).run(source);

    expect(result.status).toBe("FAILED");
    expect(result.spent_usd).toBe("0.37");
    expect(result.reason_codes).toContain("AUTO_REPAIR_BUDGET_SETTLEMENT_UNCERTAIN");
    expect(events).toEqual(["reserve", "generate", "settle", "attempt:1:REJECTED"]);
    expect([...repo.candidates.values()]).toHaveLength(0);
    expect(repo.heads.get(BRANCH)).toBe(VERSION);
  });
});
