import type { DesignDocument, DesignOperation, JsonValue } from "../../design-ir/src/index";

export type { DesignDocument, DesignOperation, JsonValue };

export const BRAND_RULE_SEVERITIES = ["HARD", "SOFT", "ADVISORY"] as const;
export type BrandRuleSeverity = (typeof BRAND_RULE_SEVERITIES)[number];

export const BRAND_RULE_SOURCES = [
  "USER_EXPLICIT",
  "APPROVED_GUIDE_EXTRACTION",
  "MANUAL_ADMIN",
  "INFERRED_PROPOSAL",
] as const;
export type BrandRuleSource = (typeof BRAND_RULE_SOURCES)[number];

export const BRAND_RULE_CATEGORIES = [
  "COLOR",
  "TYPOGRAPHY",
  "LOGO",
  "SPACING",
  "ASSET",
  "VOICE",
  "VISUAL_STYLE",
] as const;
export type BrandRuleCategory = (typeof BRAND_RULE_CATEGORIES)[number];

export const BRAND_RULE_TYPES = [
  "ALLOWED_COLOR_TOKENS",
  "FORBIDDEN_COLORS",
  "ALLOWED_FONT_ASSETS",
  "MIN_TEXT_SIZE",
  "REQUIRE_TOKEN_BINDING",
  "ALLOWED_LOGO_ASSETS",
  "LOGO_MIN_SIZE",
  "LOGO_CLEAR_SPACE",
  "LOGO_FORBID_ROTATION",
  "LOGO_FORBID_STRETCH",
  "LOGO_FORBID_RECOLOR",
  "ALLOWED_ASSETS",
  "SPACING_SCALE",
  "VOICE_VOCABULARY",
  "VOICE_FORBIDDEN_TERMS",
  "VISUAL_STYLE_GUIDANCE",
] as const;
export type BrandRuleType = (typeof BRAND_RULE_TYPES)[number];

export type BrandRuleSetStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";
export type BrandExtractionProposalStatus = "PROPOSED" | "APPROVED" | "REJECTED";

export interface BrandColorToken {
  readonly id: string;
  readonly name: string;
  readonly value: string;
  readonly roles: readonly string[];
}

export interface BrandFontToken {
  readonly id: string;
  readonly name: string;
  readonly asset_id: string;
  readonly roles: readonly string[];
  readonly fallback_asset_ids?: readonly string[];
}

export interface BrandTokenSet {
  readonly id: string;
  readonly brand_profile_id: string;
  readonly version: string;
  readonly colors: readonly BrandColorToken[];
  readonly fonts: readonly BrandFontToken[];
  readonly spacing_scale: readonly number[];
  readonly radius_tokens?: Readonly<Record<string, number>>;
}

export interface BrandAssetSet {
  readonly id: string;
  readonly brand_profile_id: string;
  readonly version: string;
  readonly logo_asset_ids: readonly string[];
  readonly font_asset_ids: readonly string[];
  readonly reference_asset_ids: readonly string[];
  readonly negative_reference_asset_ids?: readonly string[];
}

export interface BrandVoice {
  readonly tone_attributes: readonly string[];
  readonly preferred_vocabulary: readonly string[];
  readonly forbidden_terms: readonly string[];
  readonly do_examples?: readonly string[];
  readonly dont_examples?: readonly string[];
  readonly locale_overrides?: Readonly<Record<string, Readonly<Record<string, JsonValue>>>>;
}

export interface BrandVisualReferenceSet {
  readonly photography_direction?: readonly string[];
  readonly lighting?: readonly string[];
  readonly composition?: readonly string[];
  readonly background_style?: readonly string[];
  readonly texture?: readonly string[];
  readonly illustration_style?: readonly string[];
  readonly reference_asset_ids: readonly string[];
  readonly negative_reference_asset_ids: readonly string[];
}

export interface BrandProfile {
  readonly id: string;
  readonly organization_id: string;
  readonly project_id?: string | null;
  readonly name: string;
  readonly status: "ACTIVE" | "ARCHIVED";
}

export interface BrandRuleScope {
  readonly node_ids?: readonly string[];
  readonly roles?: readonly string[];
  readonly channels?: readonly string[];
  readonly locales?: readonly string[];
}

export interface BrandRuleCitation {
  readonly source_asset_id: string;
  readonly page?: number;
  readonly span?: string;
}

export interface BrandRule {
  readonly id: string;
  readonly category: BrandRuleCategory;
  readonly type: BrandRuleType;
  readonly severity: BrandRuleSeverity;
  readonly source: BrandRuleSource;
  readonly priority: number;
  readonly scope: BrandRuleScope;
  readonly parameters: Readonly<Record<string, JsonValue>>;
  readonly active: boolean;
  readonly citations?: readonly BrandRuleCitation[];
}

export interface BrandRuleSet {
  readonly id: string;
  readonly organization_id: string;
  readonly brand_profile_id: string;
  readonly version: string;
  readonly status: BrandRuleSetStatus;
  readonly token_set_version: string;
  readonly asset_set_version: string;
  readonly rules: readonly BrandRule[];
  readonly voice: BrandVoice;
  readonly visual_references: BrandVisualReferenceSet;
  readonly created_at: string;
  readonly published_at?: string;
}

export interface BrandContext {
  readonly brand_profile_id: string;
  readonly brand_rule_set_id: string;
  readonly brand_rule_set_version: string;
  readonly hard_rules: readonly BrandRule[];
  readonly selected_tokens: Readonly<Record<string, JsonValue>>;
  readonly allowed_assets: readonly string[];
  readonly voice_summary: Readonly<Record<string, JsonValue>>;
  readonly reference_asset_ids: readonly string[];
  readonly pinned: true;
}

export interface BrandDiagnostic {
  readonly rule_id: string;
  readonly severity: BrandRuleSeverity;
  readonly category: BrandRuleCategory;
  readonly reason_code: string;
  readonly node_id?: string;
  readonly expected?: JsonValue;
  readonly actual?: JsonValue;
  readonly score?: number;
  readonly repair_operations?: readonly DesignOperation[];
}

export interface BrandComplianceReport {
  readonly brand_rule_set_version: string;
  readonly decision: "PASS" | "PASS_WITH_WARNINGS" | "FAIL";
  readonly score: number;
  readonly diagnostics: readonly BrandDiagnostic[];
  readonly hard_violation_count: number;
  readonly soft_violation_count: number;
  readonly advisory_count: number;
}

export interface BrandEvaluationContext {
  readonly document: DesignDocument;
  readonly rule_set: BrandRuleSet;
  readonly token_set: BrandTokenSet;
  readonly asset_set: BrandAssetSet;
  readonly channel?: string;
  readonly locale?: string;
  readonly verified_asset_ids?: readonly string[];
  readonly font_rights_allowed_asset_ids?: readonly string[];
}

export interface BrandGuideExtractionCandidate {
  readonly candidate_id: string;
  readonly rule: BrandRule;
  readonly confidence: number;
  readonly citations: readonly BrandRuleCitation[];
}

export interface BrandGuideExtractionProposal {
  readonly id: string;
  readonly organization_id: string;
  readonly brand_profile_id: string;
  readonly source_asset_id: string;
  readonly status: BrandExtractionProposalStatus;
  readonly candidates: readonly BrandGuideExtractionCandidate[];
  readonly created_at: string;
  readonly reviewed_by?: string;
  readonly reviewed_at?: string;
}
