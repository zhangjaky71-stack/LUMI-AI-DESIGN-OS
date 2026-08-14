import { describe, expect, it } from "vitest";
import type { DesignConstraint } from "../../design-constraints/src/index";
import type { DesignDocument, DesignOperation } from "../../design-ir/src/index";
import { QualityEngine } from "../../quality-engine/src/engine";
import type { CriticSubject, QualityDimension, QualityProfile, QualityResult, QualityViolation } from "../../quality-engine/src/types";
import { MemoryRepairArtifactRepository, MemoryRepairAttemptRepository } from "./memory-repository";
import type { AutoRepairPorts, BudgetReservationPort, RepairQualityPort } from "./ports";
import { AutoRepairLoop } from "./runtime";
import type { AutoRepairPolicy, RepairSource } from "./types";

const ORG = "00000000-0000-4000-8000-000000000001";
const PROJECT = "00000000-0000-4000-8000-000000000002";
const ARTIFACT = "00000000-0000-4000-8000-000000000003";
const VERSION = "00000000-0000-4000-8000-000000000004";
const DESIGN_VERSION = "00000000-0000-4000-8000-000000000005";
const BRANCH = "00000000-0000-4000-8000-000000000006";
const NOW = "2026-08-15T00:30:00.000Z";
const H = "a".repeat(64);

function document(text = "Wrong"): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "doc-repair",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
      frame: { id: "frame", kind: "FRAME", parent_id: "root", children: ["title"], transform: { x: 0, y: 0, width: 800, height: 600 } },
      title: { id: "title", kind: "TEXT", parent_id: "frame", children: [], content: text, transform: { x: 20, y: 20, width: 200, height: 50 } },
    },
    resources: {},
    metadata: { document_version: 7 },
  };
}

function subject(doc = document()): CriticSubject {
  return {
    organization_id: ORG,
    project_id: PROJECT,
    artifact_id: ARTIFACT,
    artifact_version_id: VERSION,
    design_document_version_id: DESIGN_VERSION,
    design_document: doc,
    rendered_asset_ref: "artifact-file:source",
    width: 1200,
    height: 900,
    expected_text: ["Correct"],
  };
}

function profile(dimension: QualityDimension = "TEXT_ACCURACY"): QualityProfile {
  return {
    profile_id: `repair:${dimension}`,
    version: "1.0.0",
    name: "production-web",
    overall_pass_threshold: 90,
    overall_warning_threshold: 85,
    review_confidence_threshold: 0.7,
    dimensions: [{ dimension, weight: 1, threshold: 90, hard_gate: false, minimum_confidence: 0.7 }],
  };
}

const policy: AutoRepairPolicy = {
  policy_id: "repair-policy:production",
  version: "1.0.0",
  max_auto_repair_iterations: 3,
  max_repair_cost_usd: "1.5",
  minimum_expected_gain: 5,
  max_score_regression: 2,
};

function violation(reason = "TEXT_OVERFLOW", dimension: QualityDimension = "TEXT_ACCURACY", severity: QualityViolation["severity"] = "MAJOR"): QualityViolation {
  return { violation_id: `v:${reason}`, dimension, severity, reason_code: reason, message: reason, target_id: "title", evidence_ids: [], repairable: true };
}

function operation(id: string, content: string, expected = 7): DesignOperation {
  return { operation_id: id, type: "SET_TEXT", target_ids: ["title"], expected_document_version: expected, payload: { content }, reason: "repair fixture" };
}

function quality(input: {
  id: string;
  status: QualityResult["status"];
  score: number;
  artifactVersion?: string;
  designVersion?: string;
  violations?: readonly QualityViolation[];
  repairs?: readonly DesignOperation[];
}): QualityResult {
  return {
    quality_result_id: input.id,
    organization_id: ORG,
    project_id: PROJECT,
    artifact_id: ARTIFACT,
    artifact_version_id: input.artifactVersion ?? VERSION,
    design_document_version_id: input.designVersion ?? DESIGN_VERSION,
    profile_id: "repair:TEXT_ACCURACY",
    profile_version: "1.0.0",
    status: input.status,
    overall_score: input.score,
    confidence: 1,
    dimensions: [],
    violations: input.violations ?? [],
    strengths: [],
    repair_actions: input.repairs ?? [],
    evidence: [],
    unavailable_graders: [],
    grader_versions: { fixture: "1" },
    created_at: NOW,
  };
}

function source(q: QualityResult, doc = document(), constraints: readonly DesignConstraint[] = []): RepairSource {
  return { branch_id: BRANCH, expected_branch_head: VERSION, subject: subject(doc), quality: q, constraints };
}

function structuralMaterializer(events: string[] = []) {
  return {
    async materialize(doc: DesignDocument) {
      events.push("materialize");
      const version = Number(doc.metadata?.document_version ?? 0);
      return { rendered_asset_ref: `artifact-file:rendered:${version}`, content_hash: H, constraint_snapshot_hash: "b".repeat(64), width: 1200, height: 900 };
    },
  };
}

function loopPorts(repo: MemoryRepairArtifactRepository, qport: RepairQualityPort, events: string[] = []): AutoRepairPorts {
  return {
    artifacts: repo,
    quality: qport,
    attempts: new MemoryRepairAttemptRepository(events),
    structural_materializer: structuralMaterializer(events),
  };
}

async function realQuality(doc = document()) {
  const p = profile();
  const engine = new QualityEngine({ ports: {}, now: () => NOW });
  return { p, engine, result: await engine.evaluate({ subject: subject(doc), profile: p }) };
}

describe("NODE-51 bounded Auto Repair Loop", () => {
  it("executes NODE-50 DesignOperation through NODE-39 and promotes only after re-evaluation", async () => {
    const { p, engine, result } = await realQuality();
    expect(result.status).toBe("FAIL_REPAIRABLE");
    expect(result.repair_actions[0]?.type).toBe("SET_TEXT");
    const events: string[] = [];
    const repo = new MemoryRepairArtifactRepository(BRANCH, VERSION);
    const ports = loopPorts(repo, {
      async evaluate(candidate) {
        events.push("quality");
        expect(repo.recordByArtifactVersion(candidate.artifact_version_id)?.status).toBe("DRAFT");
        return engine.evaluate({ subject: candidate, profile: p });
      },
    }, events);
    const output = await new AutoRepairLoop(ports, { policy, now: () => NOW }).run(source(result));
    expect(output.status).toBe("SUCCEEDED");
    expect(output.iterations).toBe(1);
    expect(output.attempts[0]?.disposition).toBe("PROMOTED_READY");
    expect(repo.heads.get(BRANCH)).toBe(output.final_artifact_version_id);
    expect(repo.recordByArtifactVersion(output.final_artifact_version_id)?.status).toBe("READY");
    expect(events.indexOf("quality")).toBeGreaterThan(events.indexOf("materialize"));
    expect(repo.events.findIndex((e) => e.startsWith("persist:"))).toBeLessThan(repo.events.findIndex((e) => e.startsWith("promote:")));
  });

  it("rejects a worse candidate and keeps the source branch head", async () => {
    const before = quality({ id: "q:before", status: "FAIL_REPAIRABLE", score: 70, violations: [violation()], repairs: [operation("op:1", "Better")] });
    const repo = new MemoryRepairArtifactRepository(BRANCH, VERSION);
    const output = await new AutoRepairLoop(loopPorts(repo, { async evaluate(candidate) { return quality({ id: "q:worse", status: "FAIL_REPAIRABLE", score: 60, artifactVersion: candidate.artifact_version_id, designVersion: candidate.design_document_version_id, violations: [violation()], repairs: [] }); } }), { policy: { ...policy, max_auto_repair_iterations: 1 }, now: () => NOW }).run(source(before));
    expect(output.status).toBe("ITERATION_LIMIT");
    expect(output.attempts[0]?.reason_codes).toContain("QUALITY_REGRESSION");
    expect(repo.heads.get(BRANCH)).toBe(VERSION);
    const candidate = output.attempts[0]?.candidate_artifact_version_id;
    expect(candidate && repo.recordByArtifactVersion(candidate)?.status).toBe("REJECTED");
  });

  it("rejects a candidate that introduces a new hard violation even if score rises", async () => {
    const before = quality({ id: "q:before", status: "FAIL_REPAIRABLE", score: 55, violations: [violation()], repairs: [operation("op:1", "Better")] });
    const hard = violation("QR_PAYLOAD_CHANGED", "QR_READABILITY", "HARD");
    const repo = new MemoryRepairArtifactRepository(BRANCH, VERSION);
    const output = await new AutoRepairLoop(loopPorts(repo, { async evaluate(candidate) { return quality({ id: "q:hard", status: "FAIL_HARD", score: 95, artifactVersion: candidate.artifact_version_id, designVersion: candidate.design_document_version_id, violations: [hard] }); } }), { policy: { ...policy, max_auto_repair_iterations: 1 }, now: () => NOW }).run(source(before));
    expect(output.attempts[0]?.reason_codes).toContain("NEW_HARD_VIOLATION");
    expect(repo.heads.get(BRANCH)).toBe(VERSION);
  });

  it("allows cumulative bounded DRAFT improvement before a later READY repair", async () => {
    const first = quality({ id: "q:0", status: "FAIL_REPAIRABLE", score: 50, violations: [violation("COPY_WRONG")], repairs: [operation("op:1", "Step One")] });
    const repo = new MemoryRepairArtifactRepository(BRANCH, VERSION);
    let round = 0;
    const qport: RepairQualityPort = {
      async evaluate(candidate) {
        round += 1;
        if (round === 1) return quality({ id: "q:1", status: "FAIL_REPAIRABLE", score: 65, artifactVersion: candidate.artifact_version_id, designVersion: candidate.design_document_version_id, violations: [violation("COPY_STILL_LONG")], repairs: [operation("op:2", "Correct", 8)] });
        return quality({ id: "q:2", status: "PASS", score: 96, artifactVersion: candidate.artifact_version_id, designVersion: candidate.design_document_version_id });
      },
    };
    const output = await new AutoRepairLoop(loopPorts(repo, qport), { policy, now: () => NOW }).run(source(first));
    expect(output.status).toBe("SUCCEEDED");
    expect(output.iterations).toBe(2);
    expect(output.attempts.map((row) => row.disposition)).toEqual(["PROMOTED_DRAFT", "PROMOTED_READY"]);
    expect(repo.heads.get(BRANCH)).toBe(output.final_artifact_version_id);
  });

  it("fails closed when a paid repair cannot be reserved within loop/external budget", async () => {
    const before = quality({ id: "q:image", status: "FAIL_REPAIRABLE", score: 55, violations: [violation("BACKGROUND_NOISE", "IMAGE_DEFECTS")], repairs: [] });
    const repo = new MemoryRepairArtifactRepository(BRANCH, VERSION);
    let invoked = false;
    const output = await new AutoRepairLoop({
      artifacts: repo,
      attempts: new MemoryRepairAttemptRepository(),
      structural_materializer: structuralMaterializer(),
      quality: { async evaluate() { throw new Error("should not evaluate"); } },
      cost_estimator: { async estimate() { return "0.8"; } },
      budget: { async remaining() { return "0.2"; }, async reserve() { throw new Error("should not reserve"); }, async settle() {}, async release() {} },
      generative: { async execute() { invoked = true; throw new Error("should not execute"); } },
    }, { policy: { ...policy, max_repair_cost_usd: "0.5" }, now: () => NOW }).run(source(before));
    expect(output.status).toBe("BUDGET_EXHAUSTED");
    expect(invoked).toBe(false);
    expect(repo.heads.get(BRANCH)).toBe(VERSION);
  });

  it("reserves budget before paid generative execution and settles actual cost", async () => {
    const before = quality({ id: "q:image", status: "FAIL_REPAIRABLE", score: 55, violations: [violation("BACKGROUND_NOISE", "IMAGE_DEFECTS")], repairs: [] });
    const events: string[] = [];
    const repo = new MemoryRepairArtifactRepository(BRANCH, VERSION);
    const budget: BudgetReservationPort = {
      async remaining() { return "1.0"; },
      async reserve() { events.push("reserve"); return { reservation_id: "reservation:1", amount_usd: "0.4" }; },
      async settle(_reservation, actual) { events.push(`settle:${actual}`); },
      async release() { events.push("release"); },
    };
    const output = await new AutoRepairLoop({
      artifacts: repo,
      attempts: new MemoryRepairAttemptRepository(events),
      structural_materializer: structuralMaterializer(events),
      cost_estimator: { async estimate() { return "0.4"; } },
      budget,
      generative: { async execute(_item, current, reservationId) { events.push(`generate:${reservationId}`); return { design_document: current.subject.design_document, rendered_asset_ref: "artifact-file:edited", content_hash: "c".repeat(64), constraint_snapshot_hash: "d".repeat(64), actual_cost_usd: "0.35", width: 1200, height: 900 }; } },
      quality: { async evaluate(candidate) { events.push("quality"); return quality({ id: "q:pass", status: "PASS", score: 93, artifactVersion: candidate.artifact_version_id, designVersion: candidate.design_document_version_id }); } },
    }, { policy, now: () => NOW }).run(source(before));
    expect(output.status).toBe("SUCCEEDED");
    expect(output.spent_usd).toBe("0.35");
    expect(events.indexOf("reserve")).toBeLessThan(events.indexOf("generate:reservation:1"));
    expect(events.indexOf("generate:reservation:1")).toBeLessThan(events.indexOf("settle:0.35"));
    expect(events.indexOf("settle:0.35")).toBeLessThan(events.indexOf("quality"));
  });

  it("returns STALE_SOURCE when a concurrent user edit wins before candidate promotion", async () => {
    const before = quality({ id: "q:before", status: "FAIL_REPAIRABLE", score: 60, violations: [violation()], repairs: [operation("op:1", "Correct")] });
    const repo = new MemoryRepairArtifactRepository(BRANCH, VERSION);
    const output = await new AutoRepairLoop(loopPorts(repo, { async evaluate(candidate) { repo.simulateExternalHead(BRANCH, "00000000-0000-4000-8000-000000009999"); return quality({ id: "q:pass", status: "PASS", score: 96, artifactVersion: candidate.artifact_version_id, designVersion: candidate.design_document_version_id }); } }), { policy, now: () => NOW }).run(source(before));
    expect(output.status).toBe("STALE_SOURCE");
    expect(repo.heads.get(BRANCH)).toBe("00000000-0000-4000-8000-000000009999");
    const candidate = output.attempts[0]?.candidate_artifact_version_id;
    expect(candidate && repo.recordByArtifactVersion(candidate)?.status).toBe("REJECTED");
  });

  it("never persists a structural candidate denied by NODE-39 preflight", async () => {
    const before = quality({ id: "q:locked", status: "FAIL_REPAIRABLE", score: 50, violations: [violation("LOCKED_COPY")], repairs: [operation("op:locked", "Correct")] });
    const constraint: DesignConstraint = { id: "lock-title", type: "LOCK_TEXT", scope: { node_ids: ["title"] }, severity: "HARD", source: "USER_EXPLICIT", priority: 100, parameters: {}, active: true, document_version: 7 };
    const repo = new MemoryRepairArtifactRepository(BRANCH, VERSION);
    const output = await new AutoRepairLoop(loopPorts(repo, { async evaluate() { throw new Error("should not evaluate"); } }), { policy: { ...policy, max_auto_repair_iterations: 2 }, now: () => NOW }).run(source(before, document(), [constraint]));
    expect(output.status).toBe("REVIEW_REQUIRED");
    expect([...repo.candidates.values()]).toHaveLength(0);
    expect(repo.heads.get(BRANCH)).toBe(VERSION);
  });
});
