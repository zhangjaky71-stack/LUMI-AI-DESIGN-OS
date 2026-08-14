import type { QualityResult, QualityViolation } from "../../quality-engine/src/index";
import type { AutoRepairPolicy, QualityComparison } from "./types";

function hardKey(value: QualityViolation): string {
  return `${value.reason_code}:${value.target_id ?? "*"}`;
}

export function compareQuality(source: QualityResult, candidate: QualityResult, policy: AutoRepairPolicy): QualityComparison {
  const gain = Math.round((candidate.overall_score - source.overall_score) * 100) / 100;
  const sourceHard = new Set(source.violations.filter((item) => item.severity === "HARD").map(hardKey));
  const candidateHard = candidate.violations.filter((item) => item.severity === "HARD");
  const newHard = candidateHard.map(hardKey).filter((key) => !sourceHard.has(key)).sort();
  if (newHard.length) return { disposition: "REJECTED", score_gain: gain, new_hard_violations: newHard, reason_codes: ["NEW_HARD_VIOLATION"] };
  if (candidate.status === "REVIEW_REQUIRED") return { disposition: "REVIEW", score_gain: gain, new_hard_violations: [], reason_codes: ["QUALITY_REVIEW_REQUIRED"] };
  if (candidate.status === "FAIL_HARD") return { disposition: "REJECTED", score_gain: gain, new_hard_violations: [], reason_codes: ["HARD_VIOLATION_REMAINS"] };
  if (gain < -policy.max_score_regression) return { disposition: "REJECTED", score_gain: gain, new_hard_violations: [], reason_codes: ["QUALITY_REGRESSION"] };
  if (candidate.status === "PASS" || candidate.status === "PASS_WITH_WARNINGS") {
    return { disposition: "PROMOTED_READY", score_gain: gain, new_hard_violations: [], reason_codes: ["QUALITY_GATE_PASSED"] };
  }
  if (candidate.status === "FAIL_REPAIRABLE" && gain >= policy.minimum_expected_gain) {
    return { disposition: "PROMOTED_DRAFT", score_gain: gain, new_hard_violations: [], reason_codes: ["QUALITY_IMPROVED_CONTINUE"] };
  }
  return { disposition: "REJECTED", score_gain: gain, new_hard_violations: [], reason_codes: ["MINIMUM_GAIN_NOT_MET"] };
}
