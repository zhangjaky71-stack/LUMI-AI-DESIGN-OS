import type { ArtifactVersion } from "../../artifact-sdk/src/types";
import type { BrandComplianceReport } from "./types";
import { BrandRuleError } from "./runtime";

export interface BrandApprovalGateResult {
  readonly allowed: boolean;
  readonly reason_code?: "BRAND_RULE_VERSION_MISSING" | "BRAND_RULE_VERSION_MISMATCH" | "BRAND_HARD_VIOLATION";
}

export function evaluateBrandApprovalGate(
  version: ArtifactVersion,
  report: BrandComplianceReport,
): BrandApprovalGateResult {
  if (!version.brand_rule_set_version) return { allowed: false, reason_code: "BRAND_RULE_VERSION_MISSING" };
  if (version.brand_rule_set_version !== report.brand_rule_set_version) {
    return { allowed: false, reason_code: "BRAND_RULE_VERSION_MISMATCH" };
  }
  if (report.hard_violation_count > 0 || report.decision === "FAIL") {
    return { allowed: false, reason_code: "BRAND_HARD_VIOLATION" };
  }
  return { allowed: true };
}

export function assertBrandApprovalAllowed(version: ArtifactVersion, report: BrandComplianceReport): void {
  const gate = evaluateBrandApprovalGate(version, report);
  if (!gate.allowed) throw new BrandRuleError(gate.reason_code ?? "brand approval gate failed");
}
