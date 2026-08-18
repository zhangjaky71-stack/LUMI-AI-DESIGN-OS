import { api } from "@/lib/api/client";
import { parseProjectDetail, type ProjectDetail } from "@/lib/projects/types";
import {
  draftWire,
  parseBrandRecord,
  parseBrandRuleSet,
  parseGuideProposal,
  type BrandDraftInput,
  type BrandGuideProposal,
  type BrandRecord,
  type BrandRuleSet,
} from "@/lib/brands/types";

export async function createBrand(
  organizationId: string,
  input: { name: string; profile?: Readonly<Record<string, unknown>> },
): Promise<BrandRecord> {
  const payload = await api.post<unknown>("/api/v1/brands", {
    name: input.name,
    profile: input.profile ?? {},
  }, { headers: tenantHeaders(organizationId) });
  return parseBrandRecord(payload);
}

export async function patchBrand(
  organizationId: string,
  brand: BrandRecord,
  patch: { name?: string; profile?: Readonly<Record<string, unknown>> },
): Promise<BrandRecord> {
  const payload = await api.patch<unknown>(`/api/v1/brands/${encodeURIComponent(brand.id)}`, patch, {
    headers: {
      ...tenantHeaders(organizationId),
      "If-Match": `W/\"${brand.version}\"`,
    },
  });
  return parseBrandRecord(payload);
}

export async function createBrandDraft(
  organizationId: string,
  brandId: string,
  input: BrandDraftInput,
): Promise<BrandRuleSet> {
  const payload = await api.post<unknown>(`/api/v1/brands/${encodeURIComponent(brandId)}/rule-sets`, draftWire(input), {
    headers: tenantHeaders(organizationId),
  });
  return parseBrandRuleSet(payload);
}

export async function publishBrandRuleSet(
  organizationId: string,
  brandId: string,
  ruleSetId: string,
): Promise<BrandRuleSet> {
  const payload = await api.post<unknown>(`/api/v1/brands/${encodeURIComponent(brandId)}/rule-sets/${encodeURIComponent(ruleSetId)}/publish`, {}, {
    headers: tenantHeaders(organizationId),
  });
  return parseBrandRuleSet(payload);
}

export async function reviewGuideProposal(
  organizationId: string,
  brandId: string,
  proposalId: string,
  approve: boolean,
): Promise<BrandGuideProposal> {
  const payload = await api.post<unknown>(`/api/v1/brands/${encodeURIComponent(brandId)}/guide-proposals/${encodeURIComponent(proposalId)}/review`, { approve }, {
    headers: tenantHeaders(organizationId),
  });
  return parseGuideProposal(payload);
}

export async function publishGuideProposal(
  organizationId: string,
  brandId: string,
  proposal: BrandGuideProposal,
  base: BrandRuleSet | null,
): Promise<BrandRuleSet> {
  const tokenSet = base?.tokenSet ?? { id: crypto.randomUUID(), version: 1, tokens: [] };
  const assetSet = base?.assetSet ?? { id: crypto.randomUUID(), version: 1, allowedLogoAssetIds: [], allowedFontAssetIds: [], referenceAssetIds: [], negativeReferenceAssetIds: [] };
  const voice = base?.voice ?? { toneAttributes: [], preferredVocabulary: [], forbiddenTerms: [], doExamples: [], dontExamples: [], localeNotes: [] };
  const visualStyle = base?.visualStyle ?? { photographyDirection: [], lighting: [], composition: [], backgroundStyle: [], texture: [], illustrationStyle: [] };
  const payload = await api.post<unknown>(`/api/v1/brands/${encodeURIComponent(brandId)}/guide-proposals/${encodeURIComponent(proposal.id)}/publish`, {
    token_set: {
      id: tokenSet.id,
      version: tokenSet.version,
      tokens: tokenSet.tokens.map((token) => ({ id: token.id, value: token.value, ...(token.profile ? { profile: token.profile } : {}) })),
    },
    asset_set: {
      id: assetSet.id,
      version: assetSet.version,
      allowed_logo_asset_ids: [...assetSet.allowedLogoAssetIds],
      allowed_font_asset_ids: [...assetSet.allowedFontAssetIds],
      reference_asset_ids: [...assetSet.referenceAssetIds],
      negative_reference_asset_ids: [...assetSet.negativeReferenceAssetIds],
    },
    voice: {
      tone_attributes: [...voice.toneAttributes],
      preferred_vocabulary: [...voice.preferredVocabulary],
      forbidden_terms: [...voice.forbiddenTerms],
      do_examples: [...voice.doExamples],
      dont_examples: [...voice.dontExamples],
      locale_notes: voice.localeNotes.map(([locale, note]) => [locale, note]),
    },
    visual_style: {
      photography_direction: [...visualStyle.photographyDirection],
      lighting: [...visualStyle.lighting],
      composition: [...visualStyle.composition],
      background_style: [...visualStyle.backgroundStyle],
      texture: [...visualStyle.texture],
      illustration_style: [...visualStyle.illustrationStyle],
    },
  }, { headers: tenantHeaders(organizationId) });
  return parseBrandRuleSet(payload);
}

export async function bindProjectBrand(
  organizationId: string,
  projectId: string,
  projectVersion: number,
  brandId: string | null,
): Promise<ProjectDetail> {
  const payload = await api.patch<unknown>(`/api/v1/projects/${encodeURIComponent(projectId)}`, {
    brand_id: brandId,
  }, {
    headers: {
      ...tenantHeaders(organizationId),
      "If-Match": `W/\"${projectVersion}\"`,
    },
  });
  return parseProjectDetail(payload);
}

function tenantHeaders(organizationId: string): Record<string, string> {
  const value = organizationId.trim();
  if (!value) throw new Error("ORGANIZATION_ID_REQUIRED");
  return { "X-Organization-ID": value };
}
