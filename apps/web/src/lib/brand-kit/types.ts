import type {
  BrandAssetSet,
  BrandComplianceReport,
  BrandGuideExtractionProposal,
  BrandProfile,
  BrandRuleSet,
  BrandTokenSet,
} from "@lumi/brand-rules";

export type BrandAssetScanStatus = "QUEUED" | "SCANNING" | "READY" | "REJECTED";
export type RightsAssertion = "USER_OWNED" | "LICENSED" | "UNKNOWN";
export type LogoVariant = "PRIMARY" | "SECONDARY" | "MONOCHROME" | "ICON";
export type LogoBackground = "LIGHT" | "DARK" | "ANY";
export type FontRole = "HEADING" | "BODY" | "CJK_FALLBACK";
export type VisualReferencePolarity = "APPROVED" | "NEGATIVE";
export type VisualReferenceRole = "PRODUCT" | "PHOTOGRAPHY" | "ILLUSTRATION" | "LAYOUT";
export type BrandBindingPolicy = "CURRENT_PUBLISHED" | "PINNED";

export interface BrandKitSummary {
  readonly id: string;
  readonly name: string;
  readonly status: "ACTIVE" | "ARCHIVED";
  readonly published_version: string | null;
  readonly draft_revision: number;
}

export interface BrandLogoAsset {
  readonly asset_id: string;
  readonly file_name: string;
  readonly mime_type: string;
  readonly scan_status: BrandAssetScanStatus;
  readonly rights_assertion: RightsAssertion;
  readonly variant: LogoVariant;
  readonly preferred_background: LogoBackground;
  readonly minimum_size_px: number;
  readonly safe_zone_ratio: number;
}

export interface BrandFontAsset {
  readonly asset_id: string;
  readonly file_name: string;
  readonly family: string;
  readonly scan_status: BrandAssetScanStatus;
  readonly rights_assertion: RightsAssertion;
  readonly license_note: string | null;
  readonly roles: readonly FontRole[];
}

export interface BrandVisualAsset {
  readonly asset_id: string;
  readonly file_name: string;
  readonly mime_type: string;
  readonly scan_status: BrandAssetScanStatus;
  readonly rights_assertion: RightsAssertion;
  readonly polarity: VisualReferencePolarity;
  readonly role: VisualReferenceRole;
}

export interface BrandProjectBinding {
  readonly project_id: string;
  readonly project_name: string;
  readonly policy: BrandBindingPolicy;
  readonly pinned_rule_set_version: string | null;
  readonly resolved_rule_set_version: string | null;
}

export interface ComplianceArtifactOption {
  readonly project_id: string;
  readonly project_name: string;
  readonly artifact_id: string;
  readonly artifact_version_id: string;
  readonly title: string;
  readonly brand_rule_set_version: string;
}

export interface BrandKitDetail {
  readonly profile: BrandProfile;
  readonly draft_revision: number;
  readonly draft_token_set: BrandTokenSet;
  readonly draft_asset_set: BrandAssetSet;
  readonly draft_rule_set: BrandRuleSet;
  readonly logos: readonly BrandLogoAsset[];
  readonly fonts: readonly BrandFontAsset[];
  readonly visual_assets: readonly BrandVisualAsset[];
  readonly published_versions: readonly BrandRuleSet[];
  readonly guide_proposals: readonly BrandGuideExtractionProposal[];
  readonly project_bindings: readonly BrandProjectBinding[];
  readonly compliance_artifacts: readonly ComplianceArtifactOption[];
}

export interface BrandKitSnapshot {
  readonly brands: readonly BrandKitSummary[];
  readonly active_brand_id: string;
  readonly detail: BrandKitDetail;
}

export interface SaveBrandDraftInput {
  readonly brand_profile_id: string;
  readonly expected_draft_revision: number;
  readonly name: string;
  readonly token_set: BrandTokenSet;
  readonly rule_set: BrandRuleSet;
  readonly logos: readonly BrandLogoAsset[];
  readonly fonts: readonly BrandFontAsset[];
  readonly visual_assets: readonly BrandVisualAsset[];
}

export interface UploadBrandAssetInput {
  readonly brand_profile_id: string;
  readonly file: File;
  readonly kind: "LOGO" | "FONT" | "REFERENCE" | "GUIDE";
  readonly rights_assertion: RightsAssertion;
  readonly logo_variant?: LogoVariant;
  readonly reference_polarity?: VisualReferencePolarity;
  readonly reference_role?: VisualReferenceRole;
  readonly on_progress?: (progress: number, state: "UPLOADING" | "SCANNING" | "READY" | "FAILED") => void;
}

export interface ReviewExtractionDecision {
  readonly candidate_id: string;
  readonly decision: "APPROVE" | "REJECT";
  readonly severity?: "HARD" | "SOFT" | "ADVISORY";
}

export interface ReviewGuideProposalInput {
  readonly brand_profile_id: string;
  readonly proposal_id: string;
  readonly expected_draft_revision: number;
  readonly decisions: readonly ReviewExtractionDecision[];
}

export interface PublishBrandDraftInput {
  readonly brand_profile_id: string;
  readonly expected_draft_revision: number;
}

export interface UpdateBrandBindingInput {
  readonly brand_profile_id: string;
  readonly project_id: string;
  readonly policy: BrandBindingPolicy;
  readonly pinned_rule_set_version: string | null;
}

export interface BrandComplianceInput {
  readonly brand_profile_id: string;
  readonly artifact_version_id: string;
  readonly brand_rule_set_version: string;
}

export interface BrandKitBootstrap {
  readonly mode: "http" | "e2e";
  readonly seed: BrandKitSnapshot | null;
}

export interface BrandComplianceResult {
  readonly report: BrandComplianceReport;
  readonly project_id: string;
  readonly artifact_version_id: string;
}
