import type {
  ConstraintViolation,
  DesignConstraint,
  IdentitySimilarityValidator,
  JsonValue,
  PostflightContext,
} from "../../design-constraints/src/types";
import type { IdentityPostflightResolver, IdentityValidationReport } from "./types";

function stringParameter(constraint: DesignConstraint, key: string): string | null {
  const value = constraint.parameters[key];
  return typeof value === "string" && value.length ? value : null;
}

function assertPinnedConstraint(report: IdentityValidationReport, constraint: DesignConstraint): void {
  const identityId = stringParameter(constraint, "identity_id");
  if (!identityId) throw new Error("IDENTITY_CONSTRAINT_ID_REQUIRED");
  if (identityId !== report.identity_id) throw new Error("IDENTITY_CONSTRAINT_REPORT_MISMATCH");
  const referenceVersion = stringParameter(constraint, "reference_set_version");
  if (referenceVersion && referenceVersion !== report.reference_set_version) throw new Error("IDENTITY_REFERENCE_VERSION_MISMATCH");
  const profileId = stringParameter(constraint, "threshold_profile_id");
  if (profileId && profileId !== report.threshold_profile_id) throw new Error("IDENTITY_THRESHOLD_PROFILE_MISMATCH");
  const profileVersion = stringParameter(constraint, "threshold_profile_version");
  if (profileVersion && profileVersion !== report.threshold_profile_version) throw new Error("IDENTITY_THRESHOLD_PROFILE_VERSION_MISMATCH");
  if (typeof constraint.parameters.threshold === "number") {
    throw new Error("IDENTITY_NUMERIC_THRESHOLD_MUST_COME_FROM_CALIBRATION_PROFILE");
  }
}

function asJsonObject(value: Readonly<Record<string, JsonValue>>): Readonly<Record<string, JsonValue>> {
  return value;
}

export class CalibratedIdentityConstraintAdapter implements IdentitySimilarityValidator {
  constructor(private readonly resolver: IdentityPostflightResolver) {}

  async validate(context: PostflightContext, constraint: DesignConstraint): Promise<readonly ConstraintViolation[]> {
    const report = await this.resolver.validate(context, constraint);
    assertPinnedConstraint(report, constraint);
    if (report.status === "UNAVAILABLE") throw new Error(report.reason_code ?? "IDENTITY_VALIDATION_UNAVAILABLE");
    if (report.status === "PASS") return [];

    const firstEvidence = report.evidence_refs[0];
    const repairHint = asJsonObject({
      action: report.status === "REVIEW" ? "manual_review" : "regenerate_with_canonical_reference",
      identity_id: report.identity_id,
      reference_set_version: report.reference_set_version,
      threshold_profile_id: report.threshold_profile_id,
      threshold_profile_version: report.threshold_profile_version,
      report_id: report.report_id,
    });
    return [{
      constraint_id: constraint.id,
      type: constraint.type,
      severity: constraint.severity,
      validator: "identity-engine",
      reason_code: report.reason_code ?? (report.status === "REVIEW" ? "IDENTITY_REVIEW_REQUIRED" : "IDENTITY_SCORE_BELOW_THRESHOLD"),
      ...(context.document.root_id ? { target_id: constraint.scope.node_ids?.[0] ?? context.document.root_id } : {}),
      ...(report.identity_score === null ? {} : { score: report.identity_score }),
      threshold: report.threshold,
      expected: report.identity_id,
      actual: report.status,
      repair_hint: repairHint,
      ...(firstEvidence ? { raw_evidence_ref: firstEvidence.ref } : {}),
    }];
  }
}
