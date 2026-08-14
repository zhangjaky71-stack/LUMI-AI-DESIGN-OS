import { canonicalSha256, getDocumentVersion, type DesignOperation } from "../../design-ir/src/index";
import type { QualityViolation } from "../../quality-engine/src/index";
import type { RepairCostEstimatorPort } from "./ports";
import type { AutoRepairPolicy, RepairActionKind, RepairPlan, RepairPlanItem, RepairSource } from "./types";

function severityRank(value: QualityViolation["severity"]): number {
  return { HARD: 0, MAJOR: 1, MINOR: 2, ADVISORY: 3 }[value];
}

function actionFor(violation: QualityViolation): RepairActionKind {
  if (violation.dimension === "IMAGE_DEFECTS" || violation.dimension === "COMPOSITION" || violation.dimension === "VISUAL_HIERARCHY") return "LOCAL_IMAGE_EDIT";
  if (violation.dimension === "IDENTITY_CONSISTENCY") return "REGENERATE_ELEMENT";
  if (violation.dimension === "RESOLUTION_EXPORT_READINESS") return "RESOLUTION_UPSCALE";
  return "MANUAL_REVIEW";
}

function priority(kind: RepairActionKind): number {
  return {
    STRUCTURAL_DESIGN_OP: 10,
    LOCAL_IMAGE_EDIT: 30,
    RESOLUTION_UPSCALE: 40,
    REGENERATE_ELEMENT: 60,
    REGENERATE_ARTIFACT: 90,
    MANUAL_REVIEW: 100,
  }[kind];
}

function expectedGain(kind: RepairActionKind): number {
  return {
    STRUCTURAL_DESIGN_OP: 12,
    LOCAL_IMAGE_EDIT: 10,
    RESOLUTION_UPSCALE: 15,
    REGENERATE_ELEMENT: 18,
    REGENERATE_ARTIFACT: 20,
    MANUAL_REVIEW: 0,
  }[kind];
}

function operationTargets(operations: readonly DesignOperation[]): readonly string[] {
  return [...new Set(operations.flatMap((item) => [...item.target_ids]))].sort();
}

export async function buildRepairPlan(input: {
  readonly loop_id: string;
  readonly iteration: number;
  readonly source: RepairSource;
  readonly policy: AutoRepairPolicy;
  readonly attempted_fingerprints: ReadonlySet<string>;
  readonly estimator?: RepairCostEstimatorPort;
}): Promise<RepairPlan> {
  const { source } = input;
  const items: RepairPlanItem[] = [];
  const version = getDocumentVersion(source.subject.design_document);
  const operations = source.quality.repair_actions.filter((item) => item.expected_document_version === version);
  if (operations.length) {
    const fingerprint = await canonicalSha256({ kind: "STRUCTURAL_DESIGN_OP", operations: operations.map((item) => ({ type: item.type, target_ids: item.target_ids, payload: item.payload })) });
    if (!input.attempted_fingerprints.has(fingerprint)) {
      items.push({
        item_id: `repair-item:${fingerprint.slice(0, 24)}`,
        fingerprint,
        kind: "STRUCTURAL_DESIGN_OP",
        priority: priority("STRUCTURAL_DESIGN_OP"),
        reversible: true,
        paid: false,
        estimated_cost_usd: "0",
        expected_gain: expectedGain("STRUCTURAL_DESIGN_OP"),
        reason_codes: [...new Set(source.quality.violations.filter((item) => item.repairable).map((item) => item.reason_code))].sort(),
        target_ids: operationTargets(operations),
        operations,
      });
    }
  }

  const orderedViolations = [...source.quality.violations].sort((a, b) => severityRank(a.severity) - severityRank(b.severity) || a.violation_id.localeCompare(b.violation_id));
  for (const violation of orderedViolations) {
    const kind = actionFor(violation);
    const fingerprint = await canonicalSha256({ kind, reason_code: violation.reason_code, target_id: violation.target_id ?? null });
    if (input.attempted_fingerprints.has(fingerprint) || items.some((item) => item.fingerprint === fingerprint)) continue;
    const base = {
      item_id: `repair-item:${fingerprint.slice(0, 24)}`,
      fingerprint,
      kind,
      priority: priority(kind),
      reversible: kind !== "REGENERATE_ARTIFACT",
      paid: kind !== "MANUAL_REVIEW",
      expected_gain: expectedGain(kind),
      reason_codes: [violation.reason_code],
      target_ids: violation.target_id ? [violation.target_id] : [],
    } as const;
    if (kind === "MANUAL_REVIEW") {
      items.push({ ...base, paid: false, estimated_cost_usd: "0" });
      continue;
    }
    if (!input.estimator) {
      const manualFingerprint = await canonicalSha256({ kind: "MANUAL_REVIEW", reason_code: `COST_ESTIMATOR_UNAVAILABLE:${violation.reason_code}` });
      items.push({
        item_id: `repair-item:${manualFingerprint.slice(0, 24)}`,
        fingerprint: manualFingerprint,
        kind: "MANUAL_REVIEW",
        priority: priority("MANUAL_REVIEW"),
        reversible: true,
        paid: false,
        estimated_cost_usd: "0",
        expected_gain: 0,
        reason_codes: ["COST_ESTIMATOR_UNAVAILABLE", violation.reason_code],
        target_ids: base.target_ids,
      });
      continue;
    }
    const estimated = await input.estimator.estimate({ ...base, paid: true } as Omit<RepairPlanItem, "estimated_cost_usd">, source);
    items.push({ ...base, paid: true, estimated_cost_usd: estimated });
  }

  items.sort((a, b) => a.priority - b.priority || b.expected_gain - a.expected_gain || a.item_id.localeCompare(b.item_id));
  const planIdentity = { loop_id: input.loop_id, iteration: input.iteration, source_quality_result_id: source.quality.quality_result_id, policy_id: input.policy.policy_id, policy_version: input.policy.version, items: items.map((item) => item.fingerprint) };
  return {
    plan_id: `repair-plan:${await canonicalSha256(planIdentity)}`,
    source_quality_result_id: source.quality.quality_result_id,
    source_artifact_version_id: source.subject.artifact_version_id,
    source_design_document_version_id: source.subject.design_document_version_id,
    policy_id: input.policy.policy_id,
    policy_version: input.policy.version,
    iteration: input.iteration,
    items,
  };
}
