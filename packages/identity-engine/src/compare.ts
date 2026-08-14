import { canonicalSha256 } from "../../design-ir/src/index";
import type { IdentityCandidate, IdentitySignalScore, IdentityType } from "./types";

export interface PairwiseIdentitySignalProvider {
  readonly provider_id: string;
  readonly provider_version: string;
  readonly preprocessor_version: string;
  compare(
    left: IdentityCandidate,
    right: IdentityCandidate,
    type: IdentityType,
  ): Promise<readonly IdentitySignalScore[]>;
}

export interface IdentityComparisonReport {
  readonly comparison_id: string;
  readonly organization_id: string;
  readonly identity_type: IdentityType;
  readonly score: number;
  readonly confidence: number;
  readonly signal_scores: readonly IdentitySignalScore[];
  readonly provider_id: string;
  readonly provider_version: string;
  readonly preprocessor_version: string;
}

export async function compareIdentityCandidates(
  left: IdentityCandidate,
  right: IdentityCandidate,
  type: IdentityType,
  provider: PairwiseIdentitySignalProvider,
  signalWeights: Readonly<Record<string, number>>,
): Promise<IdentityComparisonReport> {
  if (left.organization_id !== right.organization_id) throw new Error("IDENTITY_COMPARE_TENANT_MISMATCH");
  const rows = await provider.compare(left, right, type);
  const selected = new Map<string, IdentitySignalScore>();
  for (const row of rows) {
    if (!Number.isFinite(row.score) || row.score < 0 || row.score > 100) throw new Error("IDENTITY_COMPARE_SIGNAL_INVALID");
    if (!Number.isFinite(row.confidence) || row.confidence < 0 || row.confidence > 1) throw new Error("IDENTITY_COMPARE_SIGNAL_INVALID");
    const existing = selected.get(row.signal);
    if (!existing || row.score > existing.score || (row.score === existing.score && row.confidence > existing.confidence)) selected.set(row.signal, row);
  }
  if ((type === "PRODUCT" || type === "LOGO") && selected.size < 2) throw new Error("IDENTITY_MULTI_SIGNAL_EVIDENCE_REQUIRED");
  let score = 0;
  let confidence = 0;
  let totalWeight = 0;
  for (const [signal, weight] of Object.entries(signalWeights).sort(([a], [b]) => a.localeCompare(b))) {
    const row = selected.get(signal);
    if (!row) continue;
    if (!Number.isFinite(weight) || weight <= 0) throw new Error(`IDENTITY_SIGNAL_WEIGHT_INVALID:${signal}`);
    score += row.score * weight;
    confidence += row.confidence * weight;
    totalWeight += weight;
  }
  if (!totalWeight) throw new Error("IDENTITY_NO_WEIGHTED_SIGNALS");
  score /= totalWeight;
  confidence /= totalWeight;
  const signalScores = [...selected.values()].sort((a, b) => a.signal.localeCompare(b.signal));
  const digest = await canonicalSha256({
    organization_id: left.organization_id,
    identity_type: type,
    left: { artifact_id: left.artifact.artifact_id, version: left.artifact.version },
    right: { artifact_id: right.artifact.artifact_id, version: right.artifact.version },
    provider_id: provider.provider_id,
    provider_version: provider.provider_version,
    preprocessor_version: provider.preprocessor_version,
    signal_scores: signalScores.map((row) => ({ signal: row.signal, score: row.score, confidence: row.confidence })),
  });
  return {
    comparison_id: `identity-compare:${digest}`,
    organization_id: left.organization_id,
    identity_type: type,
    score,
    confidence,
    signal_scores: signalScores,
    provider_id: provider.provider_id,
    provider_version: provider.provider_version,
    preprocessor_version: provider.preprocessor_version,
  };
}
