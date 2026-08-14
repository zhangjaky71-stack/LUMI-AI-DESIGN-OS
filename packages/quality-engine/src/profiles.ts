import { QUALITY_DIMENSIONS, type QualityDimension, type QualityProfile, type QualityProfileDimension } from "./types";

function dimensions(overrides: Partial<Record<QualityDimension, Partial<QualityProfileDimension>>>): readonly QualityProfileDimension[] {
  return QUALITY_DIMENSIONS.map((dimension) => {
    const patch = overrides[dimension] ?? {};
    return {
      dimension,
      weight: patch.weight ?? 1,
      threshold: patch.threshold ?? 75,
      hard_gate: patch.hard_gate ?? false,
      minimum_confidence: patch.minimum_confidence ?? 0.65,
    };
  });
}

export const QUALITY_PROFILES: Readonly<Record<QualityProfile["name"], QualityProfile>> = Object.freeze({
  exploration: {
    profile_id: "quality:exploration",
    version: "1.0.0",
    name: "exploration",
    overall_pass_threshold: 70,
    overall_warning_threshold: 60,
    review_confidence_threshold: 0.45,
    dimensions: dimensions({
      CONSTRAINT_COMPLIANCE: { weight: 2, threshold: 65, hard_gate: true, minimum_confidence: 0.9 },
      IDENTITY_CONSISTENCY: { weight: 0.5, threshold: 55, minimum_confidence: 0.5 },
      BRAND_CONSISTENCY: { weight: 0.5, threshold: 55, minimum_confidence: 0.5 },
    }),
  },
  "production-web": {
    profile_id: "quality:production-web",
    version: "1.0.0",
    name: "production-web",
    overall_pass_threshold: 84,
    overall_warning_threshold: 75,
    review_confidence_threshold: 0.65,
    dimensions: dimensions({
      CONSTRAINT_COMPLIANCE: { weight: 3, threshold: 100, hard_gate: true, minimum_confidence: 0.95 },
      QR_READABILITY: { weight: 2, threshold: 100, hard_gate: true, minimum_confidence: 0.95 },
      RESOLUTION_EXPORT_READINESS: { weight: 2, threshold: 90, hard_gate: true, minimum_confidence: 0.9 },
      TYPOGRAPHY_READABILITY: { weight: 2, threshold: 82 },
      TEXT_ACCURACY: { weight: 2, threshold: 95, minimum_confidence: 0.9 },
      CONTRAST: { weight: 1.5, threshold: 80 },
    }),
  },
  "brand-strict": {
    profile_id: "quality:brand-strict",
    version: "1.0.0",
    name: "brand-strict",
    overall_pass_threshold: 88,
    overall_warning_threshold: 80,
    review_confidence_threshold: 0.72,
    dimensions: dimensions({
      CONSTRAINT_COMPLIANCE: { weight: 3, threshold: 100, hard_gate: true, minimum_confidence: 0.95 },
      BRAND_CONSISTENCY: { weight: 4, threshold: 100, hard_gate: true, minimum_confidence: 0.95 },
      LOGO_INTEGRITY: { weight: 3, threshold: 95, hard_gate: true, minimum_confidence: 0.9 },
      TYPOGRAPHY_READABILITY: { weight: 2, threshold: 85 },
      VISUAL_HIERARCHY: { weight: 2, threshold: 82 },
    }),
  },
  "product-strict": {
    profile_id: "quality:product-strict",
    version: "1.0.0",
    name: "product-strict",
    overall_pass_threshold: 90,
    overall_warning_threshold: 82,
    review_confidence_threshold: 0.78,
    dimensions: dimensions({
      CONSTRAINT_COMPLIANCE: { weight: 3, threshold: 100, hard_gate: true, minimum_confidence: 0.95 },
      IDENTITY_CONSISTENCY: { weight: 5, threshold: 100, hard_gate: true, minimum_confidence: 0.95 },
      LOGO_INTEGRITY: { weight: 3, threshold: 95, hard_gate: true, minimum_confidence: 0.9 },
      IMAGE_DEFECTS: { weight: 3, threshold: 88, minimum_confidence: 0.75 },
      TEXT_ACCURACY: { weight: 2, threshold: 95, minimum_confidence: 0.9 },
    }),
  },
  print: {
    profile_id: "quality:print",
    version: "1.0.0",
    name: "print",
    overall_pass_threshold: 88,
    overall_warning_threshold: 80,
    review_confidence_threshold: 0.72,
    dimensions: dimensions({
      CONSTRAINT_COMPLIANCE: { weight: 3, threshold: 100, hard_gate: true, minimum_confidence: 0.95 },
      RESOLUTION_EXPORT_READINESS: { weight: 4, threshold: 100, hard_gate: true, minimum_confidence: 0.95 },
      TYPOGRAPHY_READABILITY: { weight: 2, threshold: 88 },
      CONTRAST: { weight: 2, threshold: 85 },
      QR_READABILITY: { weight: 2, threshold: 100, hard_gate: true, minimum_confidence: 0.95 },
    }),
  },
  "social-fast": {
    profile_id: "quality:social-fast",
    version: "1.0.0",
    name: "social-fast",
    overall_pass_threshold: 76,
    overall_warning_threshold: 68,
    review_confidence_threshold: 0.55,
    dimensions: dimensions({
      CONSTRAINT_COMPLIANCE: { weight: 2, threshold: 100, hard_gate: true, minimum_confidence: 0.9 },
      VISUAL_HIERARCHY: { weight: 2, threshold: 72, minimum_confidence: 0.55 },
      COMPOSITION: { weight: 2, threshold: 72, minimum_confidence: 0.55 },
    }),
  },
});

export function qualityProfile(name: QualityProfile["name"]): QualityProfile {
  return QUALITY_PROFILES[name];
}
