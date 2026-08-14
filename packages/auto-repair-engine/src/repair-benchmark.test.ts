import { describe, expect, it } from "vitest";
import type { DesignDocument, DesignOperation } from "../../design-ir/src/index";
import type { QualityResult } from "../../quality-engine/src/index";
import { MemoryRepairArtifactRepository, MemoryRepairAttemptRepository } from "./memory-repository";
import { AutoRepairLoop } from "./runtime";
import type { RepairSource } from "./types";

function largeDocument(): DesignDocument {
  const nodes: Record<string, DesignDocument["nodes"][string]> = {
    root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
    frame: { id: "frame", kind: "FRAME", parent_id: "root", children: [], transform: { x: 0, y: 0, width: 4000, height: 4000 } },
  };
  const children: string[] = [];
  for (let index = 0; index < 2_000; index += 1) {
    const id = `text-${index}`;
    children.push(id);
    nodes[id] = { id, kind: "TEXT", parent_id: "frame", children: [], content: index === 0 ? "Wrong" : `Label ${index}`, transform: { x: index % 100, y: Math.floor(index / 100), width: 100, height: 20 } };
  }
  nodes.frame = { ...nodes.frame!, children };
  return { schema_version: "1.0", document_id: "benchmark-doc", unit: "px", root_id: "root", nodes, resources: {}, metadata: { document_version: 11 } };
}

function quality(id: string, status: QualityResult["status"], score: number, repair_actions: readonly DesignOperation[] = [], artifactVersion = "00000000-0000-4000-8000-000000000004", designVersion = "00000000-0000-4000-8000-000000000005"): QualityResult {
  return { quality_result_id: id, organization_id: "00000000-0000-4000-8000-000000000001", project_id: "00000000-0000-4000-8000-000000000002", artifact_id: "00000000-0000-4000-8000-000000000003", artifact_version_id: artifactVersion, design_document_version_id: designVersion, profile_id: "quality:production-web", profile_version: "1.0.0", status, overall_score: score, confidence: 1, dimensions: [], violations: status === "PASS" ? [] : [{ violation_id: "v", dimension: "TEXT_ACCURACY", severity: "MAJOR", reason_code: "COPY_MISMATCH", message: "copy mismatch", target_id: "text-0", evidence_ids: [], repairable: true }], strengths: [], repair_actions, evidence: [], unavailable_graders: [], grader_versions: { benchmark: "1" }, created_at: "2026-08-15T00:00:00Z" };
}

describe("NODE-51 2k-node repair benchmark contract", () => {
  it("repairs one target without dropping any of 2,000 sibling nodes", async () => {
    const doc = largeDocument();
    const op: DesignOperation = { operation_id: "repair-benchmark-op", type: "SET_TEXT", target_ids: ["text-0"], expected_document_version: 11, payload: { content: "Correct" }, reason: "benchmark" };
    const sourceQuality = quality("quality-result:benchmark-source", "FAIL_REPAIRABLE", 60, [op]);
    const source: RepairSource = { branch_id: "00000000-0000-4000-8000-000000000006", expected_branch_head: sourceQuality.artifact_version_id, subject: { organization_id: sourceQuality.organization_id, project_id: sourceQuality.project_id, artifact_id: sourceQuality.artifact_id, artifact_version_id: sourceQuality.artifact_version_id, design_document_version_id: sourceQuality.design_document_version_id, design_document: doc, rendered_asset_ref: "benchmark:source" }, quality: sourceQuality, constraints: [] };
    const repo = new MemoryRepairArtifactRepository(source.branch_id, source.expected_branch_head);
    const started = performance.now();
    const result = await new AutoRepairLoop({
      artifacts: repo,
      attempts: new MemoryRepairAttemptRepository(),
      structural_materializer: { async materialize(candidate) { expect(Object.keys(candidate.nodes)).toHaveLength(2_002); expect(candidate.nodes["text-0"]?.content).toBe("Correct"); return { rendered_asset_ref: "benchmark:candidate", content_hash: "e".repeat(64), constraint_snapshot_hash: "f".repeat(64) }; } },
      quality: { async evaluate(candidate) { return quality("quality-result:benchmark-pass", "PASS", 96, [], candidate.artifact_version_id, candidate.design_document_version_id); } },
    }, { policy: { policy_id: "repair-policy:benchmark", version: "1", max_auto_repair_iterations: 2, max_repair_cost_usd: "0", minimum_expected_gain: 5, max_score_regression: 1 } }).run(source);
    const elapsed = performance.now() - started;
    expect(result.status).toBe("SUCCEEDED");
    expect(result.iterations).toBe(1);
    expect(result.spent_usd).toBe("0");
    expect(elapsed).toBeGreaterThanOrEqual(0);
  });
});
