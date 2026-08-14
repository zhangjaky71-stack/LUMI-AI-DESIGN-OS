import { canonicalSha256, canonicalStringify, DESIGN_OPERATION_TYPES, getDocumentVersion, type DesignOperation } from "../../design-ir/src/index";
import type { ConstraintViolation } from "../../design-constraints/src/index";
import { assertGradeCalibration } from "./calibration";
import { evaluateDeterministicSignals } from "./deterministic";
import type { QualityEnginePorts, QrQualityResult } from "./ports";
import type { CriticSubject, DeterministicSignal, HumanCalibrationSummary, QualityDimension, QualityDimensionResult, QualityEvidence, QualityProfile, QualityResult, QualitySeverity, QualityViolation, VisualGradeResult } from "./types";

export interface QualityEngineRequest {
  readonly subject: CriticSubject;
  readonly profile: QualityProfile;
  readonly generation_context?: { readonly agent_role?: string; readonly model_ref?: string; readonly prompt_version?: string };
}

export interface QualityEngineOptions {
  readonly ports: QualityEnginePorts;
  readonly calibrations?: readonly HumanCalibrationSummary[];
  readonly visual_timeout_ms?: number;
  readonly now?: () => string;
}

function clampScore(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value * 100) / 100));
}
function clampConfidence(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}
function severityRank(value: QualitySeverity): number {
  return { ADVISORY: 0, MINOR: 1, MAJOR: 2, HARD: 3 }[value];
}
function strongest(values: readonly QualitySeverity[]): QualitySeverity {
  return values.reduce<QualitySeverity>((current, value) => severityRank(value) > severityRank(current) ? value : current, "ADVISORY");
}
function constraintDimension(violation: ConstraintViolation): QualityDimension {
  if (violation.type === "REQUIRE_SCANNABILITY") return "QR_READABILITY";
  if (violation.type === "REQUIRE_CONTRAST" || violation.type === "REQUIRE_TEXT_READABILITY") return violation.type === "REQUIRE_CONTRAST" ? "CONTRAST" : "TYPOGRAPHY_READABILITY";
  if (violation.type === "REQUIRE_BRAND_COMPLIANCE" || violation.type === "LOCK_BRAND") return "BRAND_CONSISTENCY";
  if (violation.type === "REQUIRE_IDENTITY_SCORE" || violation.type === "LOCK_IDENTITY") return "IDENTITY_CONSISTENCY";
  if (violation.type === "REQUIRE_RESOLUTION") return "RESOLUTION_EXPORT_READINESS";
  return "CONSTRAINT_COMPLIANCE";
}
function violationSeverity(value: "HARD" | "SOFT" | "ADVISORY"): QualitySeverity {
  return value === "HARD" ? "HARD" : value === "SOFT" ? "MAJOR" : "ADVISORY";
}
function constraintSignals(report: Awaited<ReturnType<NonNullable<QualityEnginePorts["constraints"]>["evaluate"]>>): readonly DeterministicSignal[] {
  const grouped = new Map<QualityDimension, ConstraintViolation[]>();
  for (const violation of report.violations) {
    const dimension = constraintDimension(violation);
    grouped.set(dimension, [...(grouped.get(dimension) ?? []), violation]);
  }
  const output: DeterministicSignal[] = [];
  if (!grouped.has("CONSTRAINT_COMPLIANCE")) grouped.set("CONSTRAINT_COMPLIANCE", []);
  for (const [dimension, violations] of grouped) {
    const hard = violations.some((item) => item.severity === "HARD") || (dimension === "CONSTRAINT_COMPLIANCE" && report.decision === "FAIL");
    const unavailable = report.unavailable_validators.length > 0;
    const evidence: QualityEvidence = { evidence_id: `constraint:${dimension}`, kind: "CONSTRAINT", source: "node-39", source_version: "1.0.0", confidence: unavailable ? 0.25 : 1, data: { decision: report.decision, violation_count: violations.length, unavailable_count: report.unavailable_validators.length } };
    output.push({
      dimension,
      score: hard ? 0 : violations.length ? Math.max(20, 100 - violations.length * 20) : 100,
      confidence: evidence.confidence,
      severity: hard ? "HARD" : violations.length ? strongest(violations.map((item) => violationSeverity(item.severity))) : "ADVISORY",
      hard_fail: hard,
      reason_codes: [...new Set(violations.map((item) => item.reason_code))],
      evidence: [evidence],
      violations: violations.map((item, index) => ({ violation_id: `constraint:${item.constraint_id}:${index}`, dimension, severity: violationSeverity(item.severity), reason_code: item.reason_code, message: `${item.validator}: ${item.reason_code}`, ...(item.target_id ? { target_id: item.target_id } : {}), evidence_ids: [evidence.evidence_id], repairable: Boolean(item.repair_hint), source_constraint: item })),
    });
  }
  return output;
}
function qrSignal(result: QrQualityResult): DeterministicSignal {
  const unavailable = result.status === "UNAVAILABLE";
  const failed = result.status === "FAIL" || !result.detected || !result.payload_matches || !result.readable_at_target_size;
  const ev: QualityEvidence = { evidence_id: "qr:validation", kind: "QR", source: result.provider_id, source_version: result.provider_version, confidence: unavailable ? 0 : clampConfidence(result.confidence), ...(result.evidence_ref ? { ref: result.evidence_ref } : {}), data: { detected: result.detected, payload_matches: result.payload_matches, readable_at_target_size: result.readable_at_target_size, ...(result.quiet_zone_ok !== undefined ? { quiet_zone_ok: result.quiet_zone_ok } : {}) } };
  return { dimension: "QR_READABILITY", score: failed ? 0 : 100, confidence: ev.confidence, severity: failed ? "HARD" : "ADVISORY", hard_fail: failed && !unavailable, reason_codes: unavailable ? ["QR_VALIDATOR_UNAVAILABLE"] : failed ? ["QR_READABILITY_FAILED"] : [], evidence: [ev], violations: failed && !unavailable ? [{ violation_id: "qr:failed", dimension: "QR_READABILITY", severity: "HARD", reason_code: "QR_READABILITY_FAILED", message: "QR code is not reliably readable with the expected payload", evidence_ids: [ev.evidence_id], repairable: false }] : [] };
}
function visualSignals(grade: VisualGradeResult): readonly DeterministicSignal[] {
  return grade.dimensions.map((item) => {
    const ev: QualityEvidence = { evidence_id: `visual:${grade.grader_id}:${item.dimension}`, kind: "VISUAL_GRADER", source: grade.grader_id, source_version: grade.grader_version, confidence: clampConfidence(item.confidence), ...(item.evidence_ref ? { ref: item.evidence_ref } : {}), data: { model_provider: grade.model_provider, model_name: grade.model_name, model_version: grade.model_version, prompt_version: grade.prompt_version, calibration_dataset_version: grade.calibration_dataset_version } };
    return { dimension: item.dimension, score: clampScore(item.score), confidence: ev.confidence, severity: item.score < 60 ? "MAJOR" : item.score < 75 ? "MINOR" : "ADVISORY", hard_fail: false, reason_codes: item.reason_codes, evidence: [ev] };
  });
}
function dedupeOperations(operations: readonly DesignOperation[], version: number): readonly DesignOperation[] {
  const seen = new Set<string>();
  const result: DesignOperation[] = [];
  for (const operation of operations) {
    if (!(DESIGN_OPERATION_TYPES as readonly string[]).includes(operation.type)) continue;
    if (operation.expected_document_version !== version) continue;
    const key = canonicalStringify({ type: operation.type, target_ids: operation.target_ids, payload: operation.payload });
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(operation);
  }
  return result;
}
async function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  let handle: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([promise, new Promise<T>((_, reject) => { handle = setTimeout(() => reject(new Error("QUALITY_VISUAL_GRADER_TIMEOUT")), timeoutMs); })]);
  } finally {
    if (handle !== undefined) clearTimeout(handle);
  }
}

export class QualityEngine {
  readonly #ports: QualityEnginePorts;
  readonly #calibrations: ReadonlyMap<string, HumanCalibrationSummary>;
  readonly #visualTimeoutMs: number;
  readonly #now: () => string;

  constructor(options: QualityEngineOptions) {
    this.#ports = options.ports;
    this.#calibrations = new Map((options.calibrations ?? []).map((item) => [`${item.grader_id}:${item.grader_version}`, item]));
    this.#visualTimeoutMs = options.visual_timeout_ms ?? 12_000;
    this.#now = options.now ?? (() => new Date().toISOString());
  }

  async evaluate(request: QualityEngineRequest): Promise<QualityResult> {
    const { subject, profile } = request;
    const signals: DeterministicSignal[] = [...evaluateDeterministicSignals(subject)];
    const unavailable = new Set<string>();
    const graderVersions: Record<string, string> = { deterministic: "1.0.0" };
    const strengths: string[] = [];

    if (this.#ports.constraints) {
      try { signals.push(...constraintSignals(await this.#ports.constraints.evaluate(subject))); graderVersions.constraints = "node-39"; }
      catch { unavailable.add("constraint-runtime"); }
    } else unavailable.add("constraint-runtime");

    if (this.#ports.brand) {
      try {
        const report = await this.#ports.brand.evaluate(subject);
        graderVersions.brand = report.brand_rule_set_version;
        const ev: QualityEvidence = { evidence_id: "brand:compliance", kind: "BRAND", source: "node-43", source_version: report.brand_rule_set_version, confidence: 1, data: { decision: report.decision, hard_violation_count: report.hard_violation_count, soft_violation_count: report.soft_violation_count } };
        const hard = report.hard_violation_count > 0 || report.decision === "FAIL";
        signals.push({ dimension: "BRAND_CONSISTENCY", score: clampScore(report.score), confidence: 1, severity: hard ? "HARD" : report.soft_violation_count ? "MAJOR" : "ADVISORY", hard_fail: hard, reason_codes: [...new Set(report.diagnostics.map((item) => item.reason_code))], evidence: [ev], violations: report.diagnostics.map((item, index) => ({ violation_id: `brand:${item.rule_id}:${index}`, dimension: item.category === "LOGO" ? "LOGO_INTEGRITY" : "BRAND_CONSISTENCY", severity: violationSeverity(item.severity), reason_code: item.reason_code, message: `Brand rule ${item.rule_id}: ${item.reason_code}`, ...(item.node_id ? { target_id: item.node_id } : {}), evidence_ids: [ev.evidence_id], repairable: Boolean(item.repair_operations?.length) })), repair_operations: report.diagnostics.flatMap((item) => item.repair_operations ?? []) });
        const logo = report.diagnostics.filter((item) => item.category === "LOGO");
        if (logo.length) signals.push({ dimension: "LOGO_INTEGRITY", score: logo.some((item) => item.severity === "HARD") ? 0 : Math.max(0, 100 - logo.length * 20), confidence: 1, severity: strongest(logo.map((item) => violationSeverity(item.severity))), hard_fail: logo.some((item) => item.severity === "HARD"), reason_codes: logo.map((item) => item.reason_code), evidence: [ev] });
      } catch { unavailable.add("brand-validator"); }
    } else unavailable.add("brand-validator");

    if (this.#ports.identity) {
      try {
        const reports = await this.#ports.identity.evaluate(subject);
        if (reports.length) {
          const scoreValues = reports.map((item) => item.identity_score).filter((value): value is number => value !== null);
          const confidence = Math.min(...reports.map((item) => item.confidence));
          const hard = reports.some((item) => item.severity === "HARD" && item.status === "FAIL");
          const unavailableIdentity = reports.some((item) => item.status === "UNAVAILABLE");
          const evs: QualityEvidence[] = reports.map((item) => ({ evidence_id: `identity:${item.report_id}`, kind: "IDENTITY", source: item.provider_id, source_version: item.provider_version, confidence: item.confidence, ref: item.identity_validation_snapshot_id, data: { identity_id: item.identity_id, status: item.status, threshold_profile_version: item.threshold_profile_version, calibration_dataset_version: item.calibration_dataset_version } }));
          signals.push({ dimension: "IDENTITY_CONSISTENCY", score: scoreValues.length ? Math.min(...scoreValues) : 0, confidence: unavailableIdentity ? 0 : confidence, severity: hard ? "HARD" : reports.some((item) => item.status === "REVIEW") ? "MAJOR" : "ADVISORY", hard_fail: hard, reason_codes: reports.flatMap((item) => item.reason_code ? [item.reason_code] : item.status === "REVIEW" ? ["IDENTITY_REVIEW_REQUIRED"] : item.status === "UNAVAILABLE" ? ["IDENTITY_VALIDATOR_UNAVAILABLE"] : []), evidence: evs, violations: reports.filter((item) => item.status === "FAIL").map((item) => ({ violation_id: `identity:${item.report_id}:fail`, dimension: item.identity_type === "LOGO" ? "LOGO_INTEGRITY" : "IDENTITY_CONSISTENCY", severity: item.severity === "HARD" ? "HARD" : "MAJOR", reason_code: item.reason_code ?? "IDENTITY_FAILED", message: `${item.identity_type} identity validation failed`, evidence_ids: [`identity:${item.report_id}`], repairable: false })) });
          graderVersions.identity = reports.map((item) => `${item.provider_id}@${item.provider_version}`).sort().join(",");
        }
      } catch { unavailable.add("identity-validator"); }
    } else unavailable.add("identity-validator");

    if (this.#ports.ocr && subject.expected_text?.length) {
      try {
        const result = await this.#ports.ocr.evaluate(subject);
        graderVersions.ocr = result.provider_version;
        if (result.status === "UNAVAILABLE") unavailable.add("ocr");
        else {
          const expected = subject.expected_text;
          const actual = result.texts.map((item) => item.text);
          const missing = expected.filter((item) => !actual.includes(item));
          const confidence = result.texts.length ? Math.min(...result.texts.map((item) => item.confidence)) : 0;
          const ev: QualityEvidence = { evidence_id: "ocr:text", kind: "OCR", source: result.provider_id, source_version: result.provider_version, confidence, data: { expected_count: expected.length, detected_count: actual.length, missing_count: missing.length } };
          signals.push({ dimension: "TEXT_ACCURACY", score: Math.round(((expected.length - missing.length) / expected.length) * 100), confidence, severity: missing.length ? "MAJOR" : "ADVISORY", hard_fail: false, reason_codes: missing.length ? ["OCR_EXPECTED_TEXT_MISSING"] : [], evidence: [ev] });
        }
      } catch { unavailable.add("ocr"); }
    }

    if (this.#ports.qr) {
      try { const result = await this.#ports.qr.evaluate(subject); graderVersions.qr = result.provider_version; signals.push(qrSignal(result)); if (result.status === "UNAVAILABLE") unavailable.add("qr"); }
      catch { unavailable.add("qr"); }
    }

    if (this.#ports.visual) {
      const visual = this.#ports.visual;
      if (visual.role_id !== "visual-critic") throw new Error("QUALITY_CRITIC_ROLE_ISOLATION_REQUIRED");
      const calibration = this.#calibrations.get(`${visual.grader_id}:${visual.grader_version}`);
      if (!calibration) unavailable.add("visual-grader:uncalibrated");
      else {
        try {
          const grade = await withTimeout(visual.grade(subject, profile), this.#visualTimeoutMs);
          assertGradeCalibration(grade, calibration);
          const graderModelRef = `${grade.model_provider}/${grade.model_name}@${grade.model_version}`;
          if (request.generation_context?.model_ref === graderModelRef && request.generation_context.prompt_version === grade.prompt_version) unavailable.add("visual-grader:not-isolated");
          else {
            signals.push(...visualSignals(grade));
            strengths.push(...grade.strengths);
            graderVersions[grade.grader_id] = `${grade.grader_version}:${grade.model_version}:${grade.calibration_dataset_version}`;
          }
        } catch { unavailable.add("visual-grader"); }
      }
    } else unavailable.add("visual-grader");

    const dimensionResults: QualityDimensionResult[] = profile.dimensions.map((dimensionProfile) => {
      const matches = signals.filter((signal) => signal.dimension === dimensionProfile.dimension);
      if (!matches.length) return { dimension: dimensionProfile.dimension, score: 0, confidence: 0, threshold: dimensionProfile.threshold, weight: dimensionProfile.weight, severity: "ADVISORY", hard_gate: dimensionProfile.hard_gate, passed: false, evidence_ids: [], reason_codes: ["QUALITY_EVIDENCE_UNAVAILABLE"] };
      const confidenceWeight = matches.reduce((sum, item) => sum + Math.max(item.confidence, 0.01), 0);
      const score = matches.reduce((sum, item) => sum + item.score * Math.max(item.confidence, 0.01), 0) / confidenceWeight;
      const confidence = Math.min(...matches.map((item) => item.confidence));
      const hard = matches.some((item) => item.hard_fail);
      return { dimension: dimensionProfile.dimension, score: hard ? 0 : clampScore(score), confidence: clampConfidence(confidence), threshold: dimensionProfile.threshold, weight: dimensionProfile.weight, severity: hard ? "HARD" : strongest(matches.map((item) => item.severity)), hard_gate: dimensionProfile.hard_gate, passed: !hard && score >= dimensionProfile.threshold && confidence >= dimensionProfile.minimum_confidence, evidence_ids: matches.flatMap((item) => item.evidence.map((value) => value.evidence_id)), reason_codes: [...new Set(matches.flatMap((item) => item.reason_codes))] };
    });
    const weightTotal = dimensionResults.reduce((sum, item) => sum + item.weight, 0);
    const overall = weightTotal ? dimensionResults.reduce((sum, item) => sum + item.score * item.weight, 0) / weightTotal : 0;
    const confidence = weightTotal ? dimensionResults.reduce((sum, item) => sum + item.confidence * item.weight, 0) / weightTotal : 0;
    const allViolations: QualityViolation[] = signals.flatMap((item) => item.violations ?? []);
    const repairActions = dedupeOperations(signals.flatMap((item) => item.repair_operations ?? []), getDocumentVersion(subject.design_document));
    const hardFail = signals.some((item) => item.hard_fail) || allViolations.some((item) => item.severity === "HARD");
    const lowConfidenceHard = profile.dimensions.some((profileDimension) => profileDimension.hard_gate && (dimensionResults.find((item) => item.dimension === profileDimension.dimension)?.confidence ?? 0) < profileDimension.minimum_confidence);
    const lowOverallConfidence = confidence < profile.review_confidence_threshold;
    let status: QualityResult["status"];
    if (hardFail) status = "FAIL_HARD";
    else if (lowConfidenceHard || lowOverallConfidence) status = "REVIEW_REQUIRED";
    else if (overall >= profile.overall_pass_threshold && allViolations.length === 0) status = "PASS";
    else if (overall >= profile.overall_warning_threshold) status = "PASS_WITH_WARNINGS";
    else if (repairActions.length) status = "FAIL_REPAIRABLE";
    else status = "REVIEW_REQUIRED";
    const evidence = signals.flatMap((item) => item.evidence);
    const core = { organization_id: subject.organization_id, project_id: subject.project_id, artifact_id: subject.artifact_id, artifact_version_id: subject.artifact_version_id, design_document_version_id: subject.design_document_version_id, profile_id: profile.profile_id, profile_version: profile.version, status, overall_score: clampScore(overall), confidence: clampConfidence(confidence), dimensions: dimensionResults, violations: allViolations, strengths: [...new Set(strengths)], repair_actions: repairActions, evidence, unavailable_graders: [...unavailable].sort(), grader_versions: Object.fromEntries(Object.entries(graderVersions).sort(([a], [b]) => a.localeCompare(b))) } as const;
    const qualityResultId = `quality-result:${await canonicalSha256(core)}`;
    const result: QualityResult = { quality_result_id: qualityResultId, ...core, created_at: this.#now() };
    if (this.#ports.artifact) await this.#ports.artifact.record(result);
    return result;
  }
}
