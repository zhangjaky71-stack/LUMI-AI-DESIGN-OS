import type { QualityDimension, QualityProfile, QualityProfileDimension } from "./types";

type DimensionPatch = Omit<QualityProfileDimension, "dimension">;

function dimensions(overrides: Partial<Record<QualityDimension, Partial<DimensionPatch>>>): readonly QualityProfileDimension[] {
  return Object.entries(overrides)
    .map(([dimension, patch]) => ({
      dimension: dimension as QualityDimension,
      weight: patch?.weight ?? 1,
      threshold: patch?.threshold ?? 75,
      hard_gate: patch?.hard_gate ?? false,
      minimum_confidence: patch?.minimum_confidence ?? 0.65,
    }))
    .filter((item) => item.weight > 0)
    .sort((a, b) => a.dimension.localeCompare(b.dimension));
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
      COMPOSITION: { weight: 2, threshold: 65, minimum_confidence: 0.5 },
      VISUAL_HIERARCHY: { weight: 1.5, threshold: 65, minimum_confidence: 0.5 },
      ALIGNMENT_SPACING: { weight: 1, threshold: 65, minimum_confidence: 0.7 },
      TYPOGRAPHY_READABILITY: { weight: 1, threshold: 65, minimum_confidence: 0.6 },
      IMAGE_DEFECTS: { weight: 1, threshold: 60, minimum_confidence: 0.5 },
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
      COMPOSITION: { weight: 1.5, threshold: 80, minimum_confidence: 0.65 },
      VISUAL_HIERARCHY: { weight: 2, threshold: 82, minimum_confidence: 0.65 },
      ALIGNMENT_SPACING: { weight: 1.5, threshold: 82, minimum_confidence: 0.8 },
      TYPOGRAPHY_READABILITY: { weight: 2, threshold: 82, minimum_confidence: 0.8 },
      CONTRAST: { weight: 1.5, threshold: 80, minimum_confidence: 0.8 },
      TEXT_ACCURACY: { weight: 2, threshold: 95, minimum_confidence: 0.9 },
      QR_READABILITY: { weight: 2, threshold: 100, hard_gate: true, minimum_confidence: 0.95 },
      IMAGE_DEFECTS: { weight: 1.5, threshold: 82, minimum_confidence: 0.65 },
      RESOLUTION_EXPORT_READINESS: { weight: 2, threshold: 90, hard_gate: true, minimum_confidence: 0.9 },
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
      COMPOSITION: { weight: 1.5, threshold: 82, minimum_confidence: 0.7 },
      VISUAL_HIERARCHY: { weight: 2, threshold: 82, minimum_confidence: 0.7 },
      ALIGNMENT_SPACING: { weight: 1.5, threshold: 85, minimum_confidence: 0.8 },
      TYPOGRAPHY_READABILITY: { weight: 2, threshold: 85, minimum_confidence: 0.8 },
      CONTRAST: { weight: 1.5, threshold: 82, minimum_confidence: 0.8 },
      TEXT_ACCURACY: { weight: 2, threshold: 95, minimum_confidence: 0.9 },
      IMAGE_DEFECTS: { weight: 1, threshold: 82, minimum_confidence: 0.7 },
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
      COMPOSITION: { weight: 1.5, threshold: 82, minimum_confidence: 0.75 },
      VISUAL_HIERARCHY: { weight: 1.5, threshold: 82, minimum_confidence: 0.75 },
      TEXT_ACCURACY: { weight: 2, threshold: 95, minimum_confidence: 0.9 },
      IMAGE_DEFECTS: { weight: 3, threshold: 88, minimum_confidence: 0.75 },
      RESOLUTION_EXPORT_READINESS: { weight: 2, threshold: 90, hard_gate: true, minimum_confidence: 0.9 },
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
      COMPOSITION: { weight: 1.5, threshold: 82, minimum_confidence: 0.7 },
      ALIGNMENT_SPACING: { weight: 2, threshold: 85, minimum_confidence: 0.85 },
      TYPOGRAPHY_READABILITY: { weight: 2, threshold: 88, minimum_confidence: 0.85 },
      CONTRAST: { weight: 2, threshold: 85, minimum_confidence: 0.85 },
      TEXT_ACCURACY: { weight: 2, threshold: 98, minimum_confidence: 0.92 },
      QR_READABILITY: { weight: 2, threshold: 100, hard_gate: true, minimum_confidence: 0.95 },
      RESOLUTION_EXPORT_READINESS: { weight: 4, threshold: 100, hard_gate: true, minimum_confidence: 0.95 },
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
      COMPOSITION: { weight: 2, threshold: 72, minimum_confidence: 0.55 },
      VISUAL_HIERARCHY: { weight: 2, threshold: 72, minimum_confidence: 0.55 },
      TYPOGRAPHY_READABILITY: { weight: 1, threshold: 70, minimum_confidence: 0.6 },
      IMAGE_DEFECTS: { weight: 1, threshold: 70, minimum_confidence: 0.55 },
    }),
  },
});

export function qualityProfile(name: QualityProfile["name"]): QualityProfile {
  return QUALITY_PROFILES[name];
}
