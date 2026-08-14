import type {
  ConstraintViolation,
  DesignConstraint,
  PostflightContext,
  PostflightEvaluator,
} from "./types";

export interface QrDecodeResult {
  readonly detected: boolean;
  readonly payload?: string;
  readonly quiet_zone_modules?: number;
  readonly readable_at_target_size?: boolean;
  readonly evidence_ref?: string;
}

export interface QrDecoder {
  decode(context: PostflightContext, constraint: DesignConstraint): Promise<QrDecodeResult>;
}

export class QrScannabilityEvaluator implements PostflightEvaluator {
  readonly name = "qr-scannability";
  readonly supported_types = ["REQUIRE_SCANNABILITY"] as const;
  readonly supports_preflight = false;
  readonly supports_postflight = true;

  constructor(private readonly decoder: QrDecoder) {}

  async evaluate(context: PostflightContext, constraint: DesignConstraint): Promise<readonly ConstraintViolation[]> {
    const result = await this.decoder.decode(context, constraint);
    const expectedPayload =
      typeof constraint.parameters.payload === "string" ? constraint.parameters.payload : undefined;
    const violations: ConstraintViolation[] = [];
    if (!result.detected || !result.payload) {
      violations.push({
        constraint_id: constraint.id,
        type: constraint.type,
        severity: constraint.severity,
        validator: this.name,
        reason_code: "QR_NOT_DECODABLE",
        raw_evidence_ref: result.evidence_ref,
        repair_hint: { action: "restore_qr_or_increase_size" },
      });
      return violations;
    }
    if (expectedPayload !== undefined && result.payload !== expectedPayload) {
      violations.push({
        constraint_id: constraint.id,
        type: constraint.type,
        severity: constraint.severity,
        validator: this.name,
        reason_code: "QR_PAYLOAD_CHANGED",
        expected: expectedPayload,
        actual: result.payload,
        raw_evidence_ref: result.evidence_ref,
        repair_hint: { action: "restore_qr_payload" },
      });
    }
    if (result.readable_at_target_size === false) {
      violations.push({
        constraint_id: constraint.id,
        type: constraint.type,
        severity: constraint.severity,
        validator: this.name,
        reason_code: "QR_UNREADABLE_AT_EXPORT_SIZE",
        raw_evidence_ref: result.evidence_ref,
        repair_hint: { action: "increase_qr_export_size" },
      });
    }
    const minQuietZone =
      typeof constraint.parameters.min_quiet_zone_modules === "number"
        ? constraint.parameters.min_quiet_zone_modules
        : 4;
    if (
      typeof result.quiet_zone_modules === "number" &&
      result.quiet_zone_modules < minQuietZone
    ) {
      violations.push({
        constraint_id: constraint.id,
        type: constraint.type,
        severity: constraint.severity === "HARD" ? "SOFT" : constraint.severity,
        validator: this.name,
        reason_code: "QR_QUIET_ZONE_TOO_SMALL",
        expected: minQuietZone,
        actual: result.quiet_zone_modules,
        raw_evidence_ref: result.evidence_ref,
        repair_hint: { action: "increase_qr_quiet_zone" },
      });
    }
    return violations;
  }
}

export interface ProtectedRegionSignals {
  readonly ssim: number;
  readonly edge_difference: number;
  readonly color_delta_e: number;
  readonly embedding_similarity?: number;
  readonly evidence_ref?: string;
}

export interface ProtectedRegionComparator {
  compare(context: PostflightContext, constraint: DesignConstraint): Promise<ProtectedRegionSignals>;
}

export class ProtectedRegionEvaluator implements PostflightEvaluator {
  readonly name = "protected-region";
  readonly supported_types = ["PROTECT_REGION"] as const;
  readonly supports_preflight = false;
  readonly supports_postflight = true;

  constructor(private readonly comparator: ProtectedRegionComparator) {}

  async evaluate(context: PostflightContext, constraint: DesignConstraint): Promise<readonly ConstraintViolation[]> {
    const signals = await this.comparator.compare(context, constraint);
    const minSsim = typeof constraint.parameters.min_ssim === "number" ? constraint.parameters.min_ssim : 0.985;
    const maxEdge = typeof constraint.parameters.max_edge_difference === "number" ? constraint.parameters.max_edge_difference : 0.04;
    const maxDeltaE = typeof constraint.parameters.max_color_delta_e === "number" ? constraint.parameters.max_color_delta_e : 3;
    const minEmbedding = typeof constraint.parameters.min_embedding_similarity === "number" ? constraint.parameters.min_embedding_similarity : undefined;
    const failed =
      signals.ssim < minSsim ||
      signals.edge_difference > maxEdge ||
      signals.color_delta_e > maxDeltaE ||
      (minEmbedding !== undefined &&
        signals.embedding_similarity !== undefined &&
        signals.embedding_similarity < minEmbedding);
    if (!failed) return [];
    return [
      {
        constraint_id: constraint.id,
        type: constraint.type,
        severity: constraint.severity,
        validator: this.name,
        reason_code: "PROTECTED_REGION_CHANGED",
        score: signals.ssim,
        threshold: minSsim,
        actual: {
          ssim: signals.ssim,
          edge_difference: signals.edge_difference,
          color_delta_e: signals.color_delta_e,
          embedding_similarity: signals.embedding_similarity ?? null,
        },
        raw_evidence_ref: signals.evidence_ref,
        repair_hint: { action: "restore_protected_region" },
      },
    ];
  }
}

export class ResolutionEvaluator implements PostflightEvaluator {
  readonly name = "resolution";
  readonly supported_types = ["REQUIRE_RESOLUTION"] as const;
  readonly supports_preflight = false;
  readonly supports_postflight = true;

  async evaluate(context: PostflightContext, constraint: DesignConstraint): Promise<readonly ConstraintViolation[]> {
    const width = context.after_ref.width ?? 0;
    const height = context.after_ref.height ?? 0;
    const minWidth = typeof constraint.parameters.min_width === "number" ? constraint.parameters.min_width : 0;
    const minHeight = typeof constraint.parameters.min_height === "number" ? constraint.parameters.min_height : 0;
    if (width >= minWidth && height >= minHeight) return [];
    return [
      {
        constraint_id: constraint.id,
        type: constraint.type,
        severity: constraint.severity,
        validator: this.name,
        reason_code: "RESOLUTION_TOO_LOW",
        expected: { width: minWidth, height: minHeight },
        actual: { width, height },
        repair_hint: { action: "regenerate_or_upscale" },
      },
    ];
  }
}
