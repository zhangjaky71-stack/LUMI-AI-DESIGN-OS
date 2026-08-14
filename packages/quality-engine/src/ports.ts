import type { PostflightReport } from "../../design-constraints/src/index";
import type { BrandComplianceReport } from "../../brand-rules/src/index";
import type { IdentityValidationReport } from "../../identity-engine/src/index";
import type { CriticSubject, QualityProfile, VisualGradeResult } from "./types";

export interface ConstraintQualityPort {
  evaluate(subject: CriticSubject): Promise<PostflightReport>;
}

export interface BrandQualityPort {
  evaluate(subject: CriticSubject): Promise<BrandComplianceReport>;
}

export interface IdentityQualityPort {
  evaluate(subject: CriticSubject): Promise<readonly IdentityValidationReport[]>;
}

export interface OcrQualityResult {
  readonly provider_id: string;
  readonly provider_version: string;
  readonly status: "READY" | "UNAVAILABLE";
  readonly texts: readonly { readonly text: string; readonly confidence: number; readonly evidence_ref?: string }[];
}

export interface OcrQualityPort {
  evaluate(subject: CriticSubject): Promise<OcrQualityResult>;
}

export interface QrQualityResult {
  readonly provider_id: string;
  readonly provider_version: string;
  readonly status: "PASS" | "FAIL" | "UNAVAILABLE";
  readonly confidence: number;
  readonly detected: boolean;
  readonly payload_matches: boolean;
  readonly readable_at_target_size: boolean;
  readonly quiet_zone_ok?: boolean;
  readonly evidence_ref?: string;
}

export interface QrQualityPort {
  evaluate(subject: CriticSubject): Promise<QrQualityResult>;
}

export interface VisualGraderPort {
  readonly grader_id: string;
  readonly grader_version: string;
  readonly role_id: "visual-critic";
  grade(subject: CriticSubject, profile: QualityProfile): Promise<VisualGradeResult>;
}

export interface QualityArtifactPort {
  record(result: import("./types").QualityResult): Promise<void>;
}

export interface QualityEnginePorts {
  readonly constraints?: ConstraintQualityPort;
  readonly brand?: BrandQualityPort;
  readonly identity?: IdentityQualityPort;
  readonly ocr?: OcrQualityPort;
  readonly qr?: QrQualityPort;
  readonly visual?: VisualGraderPort;
  readonly artifact?: QualityArtifactPort;
}
