import { canonicalSha256 } from "../../design-ir/src/index";
import { DEFAULT_IDENTITY_PRIVACY_POLICY, assertReferencePrivacy } from "./privacy";
import type {
  IdentityEvidenceRef,
  IdentityPrivacyPolicy,
  IdentityReferenceSet,
  IdentitySignalProvider,
  IdentitySignalScore,
  IdentityValidationInput,
  IdentityValidationReport,
  ThresholdCalibrationProfile,
  VerifiedIdentityAsset,
} from "./types";

function assertScore(value: number, label: string): void {
  if (!Number.isFinite(value) || value < 0 || value > 100) throw new Error(`${label} must be between 0 and 100`);
}

function assertConfidence(value: number): void {
  if (!Number.isFinite(value) || value < 0 || value > 1) throw new Error("signal confidence must be between 0 and 1");
}

function validateProfile(identity: IdentityReferenceSet, profile: ThresholdCalibrationProfile, provider: IdentitySignalProvider): void {
  if (identity.status !== "PUBLISHED") throw new Error("IDENTITY_REFERENCE_SET_NOT_PUBLISHED");
  if (profile.status !== "PUBLISHED") throw new Error("IDENTITY_THRESHOLD_PROFILE_NOT_PUBLISHED");
  if (identity.organization_id !== profile.organization_id) throw new Error("IDENTITY_PROFILE_TENANT_MISMATCH");
  if (identity.type !== profile.identity_type) throw new Error("IDENTITY_PROFILE_TYPE_MISMATCH");
  if (identity.threshold_profile_id !== profile.profile_id || identity.threshold_profile_version !== profile.version) {
    throw new Error("IDENTITY_PROFILE_VERSION_MISMATCH");
  }
  if (profile.model_bundle_version !== provider.provider_version) throw new Error("IDENTITY_PROVIDER_VERSION_MISMATCH");
  if (profile.preprocessor_version !== provider.preprocessor_version) throw new Error("IDENTITY_PREPROCESSOR_VERSION_MISMATCH");
  assertScore(profile.threshold, "threshold");
  assertScore(profile.review_floor, "review_floor");
  if (profile.review_floor > profile.threshold) throw new Error("IDENTITY_REVIEW_FLOOR_INVALID");
  if (!Number.isFinite(profile.minimum_confidence) || profile.minimum_confidence < 0 || profile.minimum_confidence > 1) {
    throw new Error("IDENTITY_MINIMUM_CONFIDENCE_INVALID");
  }
  if ((identity.type === "PRODUCT" || identity.type === "LOGO") && new Set(profile.required_signals).size < 2) {
    throw new Error("IDENTITY_MULTI_SIGNAL_PROFILE_REQUIRED");
  }
}

function validateReferences(identity: IdentityReferenceSet, references: readonly VerifiedIdentityAsset[]): void {
  if (!identity.reference_views.length || !identity.canonical_asset_ids.length) throw new Error("IDENTITY_REFERENCE_SET_EMPTY");
  const views = new Map(identity.reference_views.map((view) => [`${view.asset_id}@${view.asset_version}`, view]));
  const resolved = new Set<string>();
  for (const reference of references) {
    if (reference.organization_id !== identity.organization_id) throw new Error("IDENTITY_REFERENCE_TENANT_MISMATCH");
    const key = `${reference.asset_id}@${reference.asset_version}`;
    if (!views.has(key)) throw new Error("IDENTITY_REFERENCE_VERSION_MISMATCH");
    resolved.add(reference.asset_id);
  }
  for (const assetId of identity.canonical_asset_ids) {
    if (!resolved.has(assetId)) throw new Error(`IDENTITY_CANONICAL_ASSET_UNRESOLVED:${assetId}`);
  }
}

function validateCandidateTarget(input: IdentityValidationInput): void {
  if (input.identity.type === "STYLE_REFERENCE") return;
  if (input.candidate.target_region) return;
  if (input.candidate.metadata?.target_detected === true || input.candidate.metadata?.whole_artifact_target === true) return;
  throw new Error("IDENTITY_TARGET_REGION_UNAVAILABLE");
}

function selectSignalScores(scores: readonly IdentitySignalScore[]): Map<string, IdentitySignalScore> {
  const selected = new Map<string, IdentitySignalScore>();
  for (const row of scores) {
    assertScore(row.score, `signal:${row.signal}`);
    assertConfidence(row.confidence);
    const existing = selected.get(row.signal);
    if (!existing || row.score > existing.score || (row.score === existing.score && row.confidence > existing.confidence)) {
      selected.set(row.signal, row);
    }
  }
  return selected;
}

function weightedAggregate(
  selected: ReadonlyMap<string, IdentitySignalScore>,
  profile: ThresholdCalibrationProfile,
): { score: number; confidence: number } {
  let weightedScore = 0;
  let weightedConfidence = 0;
  let totalWeight = 0;
  for (const [signal, weight] of Object.entries(profile.signal_weights).sort(([a], [b]) => a.localeCompare(b))) {
    const row = selected.get(signal);
    if (!row) continue;
    if (!Number.isFinite(weight) || weight <= 0) throw new Error(`IDENTITY_SIGNAL_WEIGHT_INVALID:${signal}`);
    weightedScore += row.score * weight;
    weightedConfidence += row.confidence * weight;
    totalWeight += weight;
  }
  if (!totalWeight) throw new Error("IDENTITY_NO_WEIGHTED_SIGNALS");
  return { score: weightedScore / totalWeight, confidence: weightedConfidence / totalWeight };
}

async function snapshotId(
  identity: IdentityReferenceSet,
  profile: ThresholdCalibrationProfile,
  provider: IdentitySignalProvider,
  selected: ReadonlyMap<string, IdentitySignalScore>,
): Promise<string> {
  const digest = await canonicalSha256({
    identity_id: identity.identity_id,
    reference_set_version: identity.version,
    threshold_profile_id: profile.profile_id,
    threshold_profile_version: profile.version,
    calibration_dataset_version: profile.calibration_dataset_version,
    provider_id: provider.provider_id,
    provider_version: provider.provider_version,
    preprocessor_version: provider.preprocessor_version,
    signals: [...selected.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([signal, value]) => ({
      signal,
      score: value.score,
      confidence: value.confidence,
      reference_view_id: value.reference_view_id ?? null,
    })),
  });
  return `identity-validation:${digest}`;
}

function collectEvidence(scores: readonly IdentitySignalScore[], profile: ThresholdCalibrationProfile): IdentityEvidenceRef[] {
  const evidence: IdentityEvidenceRef[] = [
    { kind: "CALIBRATION", ref: `${profile.calibration_dataset_version}:${profile.profile_id}@${profile.version}` },
  ];
  for (const score of scores) evidence.push(...score.evidence_refs);
  const seen = new Set<string>();
  return evidence.filter((row) => {
    const key = `${row.kind}|${row.ref}|${row.detail ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).sort((a, b) => `${a.kind}:${a.ref}`.localeCompare(`${b.kind}:${b.ref}`));
}

export class IdentityValidationRuntime {
  constructor(
    private readonly provider: IdentitySignalProvider,
    private readonly privacyPolicy: IdentityPrivacyPolicy = DEFAULT_IDENTITY_PRIVACY_POLICY,
  ) {}

  async validate(input: IdentityValidationInput): Promise<IdentityValidationReport> {
    if (input.identity.organization_id !== input.candidate.organization_id) throw new Error("IDENTITY_CANDIDATE_TENANT_MISMATCH");
    if (input.profile.scenario !== input.scenario) throw new Error("IDENTITY_SCENARIO_PROFILE_MISMATCH");
    if (input.identity.type === "STYLE_REFERENCE" && input.severity === "HARD") throw new Error("STYLE_REFERENCE_CANNOT_BE_HARD");
    assertReferencePrivacy(input.identity, this.privacyPolicy);
    validateProfile(input.identity, input.profile, this.provider);
    validateReferences(input.identity, input.references);
    validateCandidateTarget(input);

    const rawScores = await this.provider.score({
      identity: input.identity,
      references: input.references,
      candidate: input.candidate,
      profile: input.profile,
    });
    const selected = selectSignalScores(rawScores);
    const missing = input.profile.required_signals.filter((signal) => !selected.has(signal));
    if (missing.length) throw new Error(`IDENTITY_REQUIRED_SIGNAL_UNAVAILABLE:${missing.sort().join(",")}`);
    if ((input.identity.type === "PRODUCT" || input.identity.type === "LOGO") && selected.size < 2) {
      throw new Error("IDENTITY_MULTI_SIGNAL_EVIDENCE_REQUIRED");
    }

    const aggregate = weightedAggregate(selected, input.profile);
    const status = aggregate.confidence < input.profile.minimum_confidence
      ? "REVIEW"
      : aggregate.score >= input.profile.threshold
        ? "PASS"
        : aggregate.score >= input.profile.review_floor
          ? "REVIEW"
          : "FAIL";
    const orderedScores = [...selected.values()].sort((a, b) => a.signal.localeCompare(b.signal));
    const validationSnapshotId = await snapshotId(input.identity, input.profile, this.provider, selected);
    const reportDigest = await canonicalSha256({
      identity_validation_snapshot_id: validationSnapshotId,
      artifact_id: input.candidate.artifact.artifact_id,
      artifact_version: input.candidate.artifact.version,
      target_node_id: input.candidate.target_node_id ?? null,
      target_region: input.candidate.target_region ?? null,
      identity_score: aggregate.score,
      confidence: aggregate.confidence,
      status,
      severity: input.severity,
    });
    const reasonCode = status === "FAIL"
      ? "IDENTITY_SCORE_BELOW_THRESHOLD"
      : status === "REVIEW"
        ? (aggregate.confidence < input.profile.minimum_confidence ? "IDENTITY_CONFIDENCE_BELOW_MINIMUM" : "IDENTITY_REVIEW_REQUIRED")
        : undefined;
    return {
      report_id: `identity-report:${reportDigest}`,
      organization_id: input.identity.organization_id,
      identity_id: input.identity.identity_id,
      identity_type: input.identity.type,
      severity: input.severity,
      scenario: input.scenario,
      status,
      identity_score: aggregate.score,
      confidence: aggregate.confidence,
      threshold: input.profile.threshold,
      review_floor: input.profile.review_floor,
      signal_scores: orderedScores,
      reference_set_version: input.identity.version,
      threshold_profile_id: input.profile.profile_id,
      threshold_profile_version: input.profile.version,
      calibration_dataset_version: input.profile.calibration_dataset_version,
      provider_id: this.provider.provider_id,
      provider_version: this.provider.provider_version,
      preprocessor_version: this.provider.preprocessor_version,
      evidence_refs: collectEvidence(orderedScores, input.profile),
      ...(input.candidate.target_region ? { candidate_region: input.candidate.target_region } : {}),
      ...(reasonCode ? { reason_code: reasonCode } : {}),
      identity_validation_snapshot_id: validationSnapshotId,
    };
  }
}

export async function identityValidationBatchSnapshotId(reports: readonly IdentityValidationReport[]): Promise<string> {
  if (!reports.length) throw new Error("IDENTITY_VALIDATION_BATCH_EMPTY");
  const organizations = new Set(reports.map((report) => report.organization_id));
  if (organizations.size !== 1) throw new Error("IDENTITY_VALIDATION_BATCH_TENANT_MISMATCH");
  const digest = await canonicalSha256(
    [...reports]
      .sort((a, b) => a.identity_id.localeCompare(b.identity_id) || a.report_id.localeCompare(b.report_id))
      .map((report) => ({
        report_id: report.report_id,
        identity_id: report.identity_id,
        status: report.status,
        severity: report.severity,
        identity_validation_snapshot_id: report.identity_validation_snapshot_id,
      })),
  );
  return `identity-batch:${digest}`;
}
