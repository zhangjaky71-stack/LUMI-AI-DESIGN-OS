import type {
  IdentityEvidenceRef,
  IdentitySignalProvider,
  IdentitySignalRequest,
  IdentitySignalScore,
} from "./types";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, value));
}

function normalizedText(value: string): string {
  return value.normalize("NFKC").toLowerCase().replace(/\s+/g, " ").trim();
}

function tokenSimilarity(a: string, b: string): number {
  const left = new Set(normalizedText(a).split(/[^\p{L}\p{N}]+/u).filter(Boolean));
  const right = new Set(normalizedText(b).split(/[^\p{L}\p{N}]+/u).filter(Boolean));
  if (!left.size && !right.size) return 100;
  const intersection = [...left].filter((item) => right.has(item)).length;
  const union = new Set([...left, ...right]).size;
  return union ? (intersection / union) * 100 : 0;
}

function evidence(kind: IdentityEvidenceRef["kind"], ref: string, detail?: string): IdentityEvidenceRef {
  return detail === undefined ? { kind, ref } : { kind, ref, detail };
}

function parseStructuredSignals(metadata: Readonly<Record<string, unknown>> | undefined): IdentitySignalScore[] {
  const root = asRecord(metadata?.identity_signal_scores);
  if (!root) return [];
  const output: IdentitySignalScore[] = [];
  for (const [signal, raw] of Object.entries(root)) {
    if (typeof raw === "number" && Number.isFinite(raw)) {
      output.push({
        signal,
        score: clampScore(raw),
        confidence: 1,
        evidence_refs: [evidence("MODEL", `structured:${signal}`)],
      });
      continue;
    }
    const row = asRecord(raw);
    if (!row || typeof row.score !== "number" || !Number.isFinite(row.score)) continue;
    const confidence = typeof row.confidence === "number" && Number.isFinite(row.confidence)
      ? Math.max(0, Math.min(1, row.confidence))
      : 1;
    const evidenceRef = typeof row.evidence_ref === "string" ? row.evidence_ref : `structured:${signal}`;
    output.push({
      signal,
      score: clampScore(row.score),
      confidence,
      evidence_refs: [evidence("MODEL", evidenceRef)],
    });
  }
  return output;
}

function exactHashSignal(request: IdentitySignalRequest): IdentitySignalScore | null {
  const metadata = request.candidate.artifact.metadata;
  const candidateChecksum = typeof metadata?.checksum_sha256 === "string" ? metadata.checksum_sha256 : null;
  if (!candidateChecksum) return null;
  const matched = request.references.find((reference) => reference.checksum_sha256 === candidateChecksum);
  const matchedViewId = matched
    ? request.identity.reference_views.find(
      (view) => view.asset_id === matched.asset_id && view.asset_version === matched.asset_version,
    )?.view_id
    : undefined;
  return {
    signal: "exact_hash",
    score: matched ? 100 : 0,
    confidence: 1,
    ...(matchedViewId ? { reference_view_id: matchedViewId } : {}),
    evidence_refs: [evidence("HASH", `sha256:${candidateChecksum}`, matched ? "exact canonical asset match" : "no canonical checksum match")],
  };
}

function wordmarkSignal(request: IdentitySignalRequest): IdentitySignalScore | null {
  const candidateText = request.candidate.artifact.metadata?.ocr_text;
  if (typeof candidateText !== "string") return null;
  const references = request.references
    .map((reference) => reference.metadata?.ocr_text)
    .filter((value): value is string => typeof value === "string");
  if (!references.length) return null;
  const scored = references.map((text) => ({ text, score: tokenSimilarity(candidateText, text) })).sort((a, b) => b.score - a.score);
  const best = scored[0];
  if (!best) return null;
  return {
    signal: "ocr_wordmark",
    score: best.score,
    confidence: 0.95,
    evidence_refs: [evidence("OCR", `ocr:${normalizedText(candidateText)}`, `closest canonical text: ${normalizedText(best.text)}`)],
  };
}

/**
 * Concrete provider for NODE-44's synchronous boundary. It computes exact hash
 * and OCR signals directly, and consumes versioned structured visual signals
 * produced by registered CV/VLM adapters (and later NODE-45 analyzers).
 */
export class StructuredIdentitySignalProvider implements IdentitySignalProvider {
  constructor(
    readonly provider_id: string,
    readonly provider_version: string,
    readonly preprocessor_version: string,
  ) {}

  async score(request: IdentitySignalRequest): Promise<readonly IdentitySignalScore[]> {
    const signals = parseStructuredSignals(request.candidate.metadata);
    const exact = exactHashSignal(request);
    if (exact) signals.push(exact);
    const wordmark = wordmarkSignal(request);
    if (wordmark) signals.push(wordmark);
    return signals.sort((a, b) => a.signal.localeCompare(b.signal) || b.score - a.score);
  }
}
