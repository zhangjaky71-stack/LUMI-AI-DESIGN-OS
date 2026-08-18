export type BrandRecord = {
  id: string;
  organizationId: string;
  name: string;
  profile: Readonly<Record<string, unknown>>;
  activeRuleSetVersionId: string | null;
  version: number;
  createdAt: string;
  updatedAt: string;
};

export type BrandToken = { id: string; value: string; profile?: string | null };
export type BrandTokenSet = { id: string; version: number; tokens: readonly BrandToken[] };
export type BrandAssetSet = {
  id: string;
  version: number;
  allowedLogoAssetIds: readonly string[];
  allowedFontAssetIds: readonly string[];
  referenceAssetIds: readonly string[];
  negativeReferenceAssetIds: readonly string[];
};
export type BrandVoice = {
  toneAttributes: readonly string[];
  preferredVocabulary: readonly string[];
  forbiddenTerms: readonly string[];
  doExamples: readonly string[];
  dontExamples: readonly string[];
  localeNotes: readonly [string, string][];
};
export type BrandVisualStyle = {
  photographyDirection: readonly string[];
  lighting: readonly string[];
  composition: readonly string[];
  backgroundStyle: readonly string[];
  texture: readonly string[];
  illustrationStyle: readonly string[];
};
export type BrandRule = {
  id: string;
  key: string;
  kind: string;
  severity: "HARD" | "SOFT" | "ADVISORY";
  source: string;
  parameters: Readonly<Record<string, unknown>>;
  description?: string | null;
};
export type BrandRuleSet = {
  id: string;
  organizationId: string;
  brandId: string;
  version: number;
  status: "DRAFT" | "PUBLISHED" | "RETIRED";
  source: string;
  tokenSet: BrandTokenSet;
  assetSet: BrandAssetSet;
  rules: readonly BrandRule[];
  voice: BrandVoice;
  visualStyle: BrandVisualStyle;
  sourceProposalId?: string | null;
  createdBy: string;
  createdAt: string;
  publishedAt?: string | null;
  publishedBy?: string | null;
  snapshotHash: string;
};
export type GuideCitation = {
  sourceAssetId: string;
  pageNumber: number;
  chunkRef: string;
  evidenceHash: string;
};
export type BrandGuideProposal = {
  id: string;
  organizationId: string;
  brandId: string;
  sourceAssetId: string;
  status: "PENDING_REVIEW" | "APPROVED" | "REJECTED" | "PUBLISHED";
  rules: readonly BrandRule[];
  citations: readonly GuideCitation[];
  createdAt: string;
  reviewedBy?: string | null;
  reviewedAt?: string | null;
};

export type BrandDraftInput = {
  source: "USER_EXPLICIT" | "MANUAL_ADMIN";
  tokenSet: BrandTokenSet;
  assetSet: BrandAssetSet;
  rules: readonly BrandRule[];
  voice: BrandVoice;
  visualStyle: BrandVisualStyle;
};

export function parseBrandRecord(value: unknown): BrandRecord {
  const record = object(value, "BRAND_INVALID");
  return {
    id: string(record.id, "BRAND_ID_REQUIRED"),
    organizationId: string(record.organization_id ?? record.organizationId, "BRAND_ORG_REQUIRED"),
    name: string(record.name, "BRAND_NAME_REQUIRED"),
    profile: object(record.profile ?? {}, "BRAND_PROFILE_INVALID"),
    activeRuleSetVersionId: optionalString(record.active_rule_set_version_id ?? record.activeRuleSetVersionId),
    version: integer(record.version, "BRAND_VERSION_INVALID", 1),
    createdAt: string(record.created_at ?? record.createdAt, "BRAND_CREATED_AT_REQUIRED"),
    updatedAt: string(record.updated_at ?? record.updatedAt, "BRAND_UPDATED_AT_REQUIRED"),
  };
}

export function parseBrandPage(value: unknown): readonly BrandRecord[] {
  const record = object(value, "BRAND_PAGE_INVALID");
  const items = array(record.items, "BRAND_ITEMS_INVALID");
  return items.map(parseBrandRecord);
}

export function parseBrandRuleSet(value: unknown): BrandRuleSet {
  const record = object(value, "BRAND_RULE_SET_INVALID");
  const status = enumString(record.status, ["DRAFT", "PUBLISHED", "RETIRED"] as const, "BRAND_RULE_SET_STATUS_INVALID");
  return {
    id: string(record.id, "BRAND_RULE_SET_ID_REQUIRED"),
    organizationId: string(record.organization_id ?? record.organizationId, "BRAND_RULE_SET_ORG_REQUIRED"),
    brandId: string(record.brand_id ?? record.brandId, "BRAND_RULE_SET_BRAND_REQUIRED"),
    version: integer(record.version, "BRAND_RULE_SET_VERSION_INVALID", 1),
    status,
    source: string(record.source, "BRAND_RULE_SET_SOURCE_REQUIRED"),
    tokenSet: parseTokenSet(record.token_set ?? record.tokenSet),
    assetSet: parseAssetSet(record.asset_set ?? record.assetSet),
    rules: array(record.rules, "BRAND_RULES_INVALID").map(parseRule),
    voice: parseVoice(record.voice ?? {}),
    visualStyle: parseVisualStyle(record.visual_style ?? record.visualStyle ?? {}),
    sourceProposalId: optionalString(record.source_proposal_id ?? record.sourceProposalId),
    createdBy: string(record.created_by ?? record.createdBy, "BRAND_RULE_SET_CREATOR_REQUIRED"),
    createdAt: string(record.created_at ?? record.createdAt, "BRAND_RULE_SET_CREATED_AT_REQUIRED"),
    publishedAt: optionalString(record.published_at ?? record.publishedAt),
    publishedBy: optionalString(record.published_by ?? record.publishedBy),
    snapshotHash: sha256(record.snapshot_hash ?? record.snapshotHash),
  };
}

export function parseGuideProposal(value: unknown): BrandGuideProposal {
  const record = object(value, "BRAND_PROPOSAL_INVALID");
  return {
    id: string(record.id, "BRAND_PROPOSAL_ID_REQUIRED"),
    organizationId: string(record.organization_id ?? record.organizationId, "BRAND_PROPOSAL_ORG_REQUIRED"),
    brandId: string(record.brand_id ?? record.brandId, "BRAND_PROPOSAL_BRAND_REQUIRED"),
    sourceAssetId: string(record.source_asset_id ?? record.sourceAssetId, "BRAND_PROPOSAL_ASSET_REQUIRED"),
    status: enumString(record.status, ["PENDING_REVIEW", "APPROVED", "REJECTED", "PUBLISHED"] as const, "BRAND_PROPOSAL_STATUS_INVALID"),
    rules: array(record.rules, "BRAND_PROPOSAL_RULES_INVALID").map(parseRule),
    citations: array(record.citations, "BRAND_PROPOSAL_CITATIONS_INVALID").map((entry) => {
      const item = object(entry, "BRAND_CITATION_INVALID");
      return {
        sourceAssetId: string(item.source_asset_id ?? item.sourceAssetId, "BRAND_CITATION_ASSET_REQUIRED"),
        pageNumber: integer(item.page_number ?? item.pageNumber, "BRAND_CITATION_PAGE_INVALID", 1),
        chunkRef: string(item.chunk_ref ?? item.chunkRef, "BRAND_CITATION_CHUNK_REQUIRED"),
        evidenceHash: sha256(item.evidence_hash ?? item.evidenceHash),
      };
    }),
    createdAt: string(record.created_at ?? record.createdAt, "BRAND_PROPOSAL_CREATED_AT_REQUIRED"),
    reviewedBy: optionalString(record.reviewed_by ?? record.reviewedBy),
    reviewedAt: optionalString(record.reviewed_at ?? record.reviewedAt),
  };
}

export function draftWire(input: BrandDraftInput): Record<string, unknown> {
  return {
    source: input.source,
    token_set: {
      id: input.tokenSet.id,
      version: input.tokenSet.version,
      tokens: input.tokenSet.tokens.map((token) => ({ id: token.id, value: token.value, ...(token.profile ? { profile: token.profile } : {}) })),
    },
    asset_set: {
      id: input.assetSet.id,
      version: input.assetSet.version,
      allowed_logo_asset_ids: [...input.assetSet.allowedLogoAssetIds],
      allowed_font_asset_ids: [...input.assetSet.allowedFontAssetIds],
      reference_asset_ids: [...input.assetSet.referenceAssetIds],
      negative_reference_asset_ids: [...input.assetSet.negativeReferenceAssetIds],
    },
    rules: input.rules.map((rule) => ({
      id: rule.id,
      key: rule.key,
      kind: rule.kind,
      severity: rule.severity,
      source: rule.source,
      parameters: structuredClone(rule.parameters),
      ...(rule.description ? { description: rule.description } : {}),
    })),
    voice: voiceWire(input.voice),
    visual_style: visualStyleWire(input.visualStyle),
  };
}

function parseTokenSet(value: unknown): BrandTokenSet {
  const record = object(value, "BRAND_TOKEN_SET_INVALID");
  return {
    id: string(record.id, "BRAND_TOKEN_SET_ID_REQUIRED"),
    version: integer(record.version, "BRAND_TOKEN_SET_VERSION_INVALID", 1),
    tokens: array(record.tokens ?? [], "BRAND_TOKENS_INVALID").map((entry) => {
      const item = object(entry, "BRAND_TOKEN_INVALID");
      return { id: string(item.id, "BRAND_TOKEN_ID_REQUIRED"), value: string(item.value, "BRAND_TOKEN_VALUE_REQUIRED"), profile: optionalString(item.profile) };
    }),
  };
}
function parseAssetSet(value: unknown): BrandAssetSet {
  const record = object(value, "BRAND_ASSET_SET_INVALID");
  return {
    id: string(record.id, "BRAND_ASSET_SET_ID_REQUIRED"),
    version: integer(record.version, "BRAND_ASSET_SET_VERSION_INVALID", 1),
    allowedLogoAssetIds: stringArray(record.allowed_logo_asset_ids ?? record.allowedLogoAssetIds ?? [], "BRAND_LOGO_ASSETS_INVALID"),
    allowedFontAssetIds: stringArray(record.allowed_font_asset_ids ?? record.allowedFontAssetIds ?? [], "BRAND_FONT_ASSETS_INVALID"),
    referenceAssetIds: stringArray(record.reference_asset_ids ?? record.referenceAssetIds ?? [], "BRAND_REFERENCE_ASSETS_INVALID"),
    negativeReferenceAssetIds: stringArray(record.negative_reference_asset_ids ?? record.negativeReferenceAssetIds ?? [], "BRAND_NEGATIVE_ASSETS_INVALID"),
  };
}
function parseVoice(value: unknown): BrandVoice {
  const record = object(value, "BRAND_VOICE_INVALID");
  const localeNotes = array(record.locale_notes ?? record.localeNotes ?? [], "BRAND_LOCALE_NOTES_INVALID").map((entry) => {
    const pair = array(entry, "BRAND_LOCALE_NOTE_INVALID");
    if (pair.length !== 2 || !pair.every((item) => typeof item === "string")) throw new Error("BRAND_LOCALE_NOTE_INVALID");
    return [pair[0] as string, pair[1] as string] as [string, string];
  });
  return {
    toneAttributes: stringArray(record.tone_attributes ?? record.toneAttributes ?? [], "BRAND_TONE_INVALID"),
    preferredVocabulary: stringArray(record.preferred_vocabulary ?? record.preferredVocabulary ?? [], "BRAND_VOCAB_INVALID"),
    forbiddenTerms: stringArray(record.forbidden_terms ?? record.forbiddenTerms ?? [], "BRAND_FORBIDDEN_TERMS_INVALID"),
    doExamples: stringArray(record.do_examples ?? record.doExamples ?? [], "BRAND_DO_EXAMPLES_INVALID"),
    dontExamples: stringArray(record.dont_examples ?? record.dontExamples ?? [], "BRAND_DONT_EXAMPLES_INVALID"),
    localeNotes,
  };
}
function parseVisualStyle(value: unknown): BrandVisualStyle {
  const record = object(value, "BRAND_VISUAL_STYLE_INVALID");
  return {
    photographyDirection: stringArray(record.photography_direction ?? record.photographyDirection ?? [], "BRAND_PHOTOGRAPHY_INVALID"),
    lighting: stringArray(record.lighting ?? [], "BRAND_LIGHTING_INVALID"),
    composition: stringArray(record.composition ?? [], "BRAND_COMPOSITION_INVALID"),
    backgroundStyle: stringArray(record.background_style ?? record.backgroundStyle ?? [], "BRAND_BACKGROUND_INVALID"),
    texture: stringArray(record.texture ?? [], "BRAND_TEXTURE_INVALID"),
    illustrationStyle: stringArray(record.illustration_style ?? record.illustrationStyle ?? [], "BRAND_ILLUSTRATION_INVALID"),
  };
}
function parseRule(value: unknown): BrandRule {
  const record = object(value, "BRAND_RULE_INVALID");
  return {
    id: string(record.id, "BRAND_RULE_ID_REQUIRED"),
    key: string(record.key, "BRAND_RULE_KEY_REQUIRED"),
    kind: string(record.kind, "BRAND_RULE_KIND_REQUIRED"),
    severity: enumString(record.severity, ["HARD", "SOFT", "ADVISORY"] as const, "BRAND_RULE_SEVERITY_INVALID"),
    source: string(record.source, "BRAND_RULE_SOURCE_REQUIRED"),
    parameters: object(record.parameters ?? {}, "BRAND_RULE_PARAMETERS_INVALID"),
    description: optionalString(record.description),
  };
}
function voiceWire(value: BrandVoice) { return { tone_attributes: [...value.toneAttributes], preferred_vocabulary: [...value.preferredVocabulary], forbidden_terms: [...value.forbiddenTerms], do_examples: [...value.doExamples], dont_examples: [...value.dontExamples], locale_notes: value.localeNotes.map(([locale, note]) => [locale, note]) }; }
function visualStyleWire(value: BrandVisualStyle) { return { photography_direction: [...value.photographyDirection], lighting: [...value.lighting], composition: [...value.composition], background_style: [...value.backgroundStyle], texture: [...value.texture], illustration_style: [...value.illustrationStyle] }; }
function object(value: unknown, code: string): Record<string, unknown> { if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(code); return value as Record<string, unknown>; }
function array(value: unknown, code: string): unknown[] { if (!Array.isArray(value)) throw new Error(code); return value; }
function string(value: unknown, code: string): string { if (typeof value !== "string" || !value.trim()) throw new Error(code); return value; }
function optionalString(value: unknown): string | null { if (value === undefined || value === null) return null; if (typeof value !== "string") throw new Error("OPTIONAL_STRING_INVALID"); return value; }
function integer(value: unknown, code: string, min: number): number { if (!Number.isInteger(value) || (value as number) < min) throw new Error(code); return value as number; }
function stringArray(value: unknown, code: string): string[] { const items = array(value, code); if (!items.every((item) => typeof item === "string")) throw new Error(code); return items as string[]; }
function sha256(value: unknown): string { const text = string(value, "SHA256_REQUIRED"); if (!/^[0-9a-f]{64}$/.test(text)) throw new Error("SHA256_INVALID"); return text; }
function enumString<const T extends readonly string[]>(value: unknown, values: T, code: string): T[number] { if (typeof value !== "string" || !values.includes(value)) throw new Error(code); return value as T[number]; }
