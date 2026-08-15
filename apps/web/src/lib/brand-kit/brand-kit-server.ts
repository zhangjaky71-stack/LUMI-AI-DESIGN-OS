import type { BrandRuleSet } from "@lumi/brand-rules";
import type { BrandKitBootstrap, BrandKitSnapshot } from "./types";

function publishedRuleSet(): BrandRuleSet {
  return {
    id: "brand-rules:lumi-coffee:1",
    organization_id: "org-lumi",
    brand_profile_id: "brand-lumi-coffee",
    version: "1.0.0",
    status: "PUBLISHED",
    token_set_version: "tokens-1.0.0",
    asset_set_version: "assets-1.0.0",
    rules: [
      {
        id: "rule-color-allowed",
        category: "COLOR",
        type: "ALLOWED_COLOR_TOKENS",
        severity: "HARD",
        source: "USER_EXPLICIT",
        priority: 100,
        scope: {},
        parameters: { token_ids: ["color-ink", "color-oat", "color-amber"] },
        active: true,
      },
      {
        id: "rule-logo-rotation",
        category: "LOGO",
        type: "LOGO_FORBID_ROTATION",
        severity: "HARD",
        source: "USER_EXPLICIT",
        priority: 90,
        scope: { roles: ["logo"] },
        parameters: {},
        active: true,
      },
      {
        id: "rule-voice-terms",
        category: "VOICE",
        type: "VOICE_FORBIDDEN_TERMS",
        severity: "SOFT",
        source: "USER_EXPLICIT",
        priority: 60,
        scope: { locales: ["zh-CN", "en"] },
        parameters: { terms: ["全网最低", "绝对最佳"] },
        active: true,
      },
    ],
    voice: {
      tone_attributes: ["克制", "温暖", "专业"],
      preferred_vocabulary: ["季节限定", "风味", "手作"],
      forbidden_terms: ["全网最低", "绝对最佳"],
      do_examples: ["以清晰、具体的风味语言描述产品。"],
      dont_examples: ["避免夸张、不可验证的绝对化承诺。"],
      locale_overrides: { en: { tone: "warm, precise, restrained" } },
    },
    visual_references: {
      photography_direction: ["自然侧光", "低饱和食物摄影"],
      lighting: ["soft daylight"],
      composition: ["large negative space", "product-first"],
      background_style: ["warm neutral"],
      texture: ["paper", "matte"],
      reference_asset_ids: ["asset-ref-photo-1"],
      negative_reference_asset_ids: ["asset-ref-negative-1"],
    },
    created_at: "2026-08-12T01:00:00.000Z",
    published_at: "2026-08-12T02:00:00.000Z",
  };
}

function draftRuleSetFrom(published: BrandRuleSet): BrandRuleSet {
  const { published_at: publishedAt, ...base } = published;
  void publishedAt;
  return {
    ...base,
    id: "brand-rules:lumi-coffee:draft-2",
    version: "2.0.0-draft",
    status: "DRAFT",
    token_set_version: "tokens-2.0.0-draft",
    asset_set_version: "assets-2.0.0-draft",
    created_at: "2026-08-15T03:00:00.000Z",
  };
}

function seed(): BrandKitSnapshot {
  const published = publishedRuleSet();
  return {
    brands: [
      {
        id: "brand-lumi-coffee",
        name: "LUMI Coffee",
        status: "ACTIVE",
        published_version: "1.0.0",
        draft_revision: 3,
      },
      {
        id: "brand-northstar-studio",
        name: "Northstar Studio",
        status: "ACTIVE",
        published_version: null,
        draft_revision: 1,
      },
    ],
    active_brand_id: "brand-lumi-coffee",
    detail: {
      profile: {
        id: "brand-lumi-coffee",
        organization_id: "org-lumi",
        project_id: null,
        name: "LUMI Coffee",
        status: "ACTIVE",
      },
      draft_revision: 3,
      draft_token_set: {
        id: "brand-tokens:lumi-coffee:draft-2",
        brand_profile_id: "brand-lumi-coffee",
        version: "tokens-2.0.0-draft",
        colors: [
          {
            id: "color-ink",
            name: "Ink",
            value: "#1C1917",
            roles: ["text", "dark-background"],
          },
          {
            id: "color-oat",
            name: "Oat",
            value: "#F3EBDD",
            roles: ["surface", "light-background"],
          },
          {
            id: "color-amber",
            name: "Amber",
            value: "#D9A441",
            roles: ["accent", "campaign"],
          },
        ],
        fonts: [
          {
            id: "font-heading",
            name: "LUMI Grotesk",
            asset_id: "asset-font-lumi-grotesk",
            roles: ["heading", "body"],
            fallback_asset_ids: ["asset-font-cjk-system"],
          },
        ],
        spacing_scale: [4, 8, 12, 16, 24, 32, 48, 64],
        radius_tokens: { small: 8, medium: 16, large: 28 },
      },
      draft_asset_set: {
        id: "brand-assets:lumi-coffee:draft-2",
        brand_profile_id: "brand-lumi-coffee",
        version: "assets-2.0.0-draft",
        logo_asset_ids: ["asset-logo-primary", "asset-logo-mono"],
        font_asset_ids: ["asset-font-lumi-grotesk", "asset-font-cjk-system"],
        reference_asset_ids: ["asset-ref-photo-1"],
        negative_reference_asset_ids: ["asset-ref-negative-1"],
      },
      draft_rule_set: draftRuleSetFrom(published),
      logos: [
        {
          asset_id: "asset-logo-primary",
          file_name: "lumi-primary.svg",
          mime_type: "image/svg+xml",
          scan_status: "READY",
          rights_assertion: "USER_OWNED",
          variant: "PRIMARY",
          preferred_background: "LIGHT",
          minimum_size_px: 72,
          safe_zone_ratio: 0.18,
        },
        {
          asset_id: "asset-logo-mono",
          file_name: "lumi-mono.svg",
          mime_type: "image/svg+xml",
          scan_status: "READY",
          rights_assertion: "USER_OWNED",
          variant: "MONOCHROME",
          preferred_background: "ANY",
          minimum_size_px: 56,
          safe_zone_ratio: 0.16,
        },
      ],
      fonts: [
        {
          asset_id: "asset-font-lumi-grotesk",
          file_name: "LumiGrotesk-Regular.woff2",
          family: "LUMI Grotesk",
          scan_status: "READY",
          rights_assertion: "LICENSED",
          license_note: "Commercial web + campaign license recorded.",
          roles: ["HEADING", "BODY"],
        },
        {
          asset_id: "asset-font-cjk-system",
          file_name: "SourceHanSansSC-Regular.otf",
          family: "Source Han Sans SC",
          scan_status: "READY",
          rights_assertion: "LICENSED",
          license_note: "Open font license metadata verified.",
          roles: ["CJK_FALLBACK"],
        },
      ],
      visual_assets: [
        {
          asset_id: "asset-ref-photo-1",
          file_name: "approved-daylight.jpg",
          mime_type: "image/jpeg",
          scan_status: "READY",
          rights_assertion: "USER_OWNED",
          polarity: "APPROVED",
          role: "PHOTOGRAPHY",
        },
        {
          asset_id: "asset-ref-negative-1",
          file_name: "avoid-neon-layout.jpg",
          mime_type: "image/jpeg",
          scan_status: "READY",
          rights_assertion: "USER_OWNED",
          polarity: "NEGATIVE",
          role: "LAYOUT",
        },
      ],
      published_versions: [published],
      guide_proposals: [],
      project_bindings: [
        {
          project_id: "project-summer-launch",
          project_name: "夏季新品发布",
          policy: "CURRENT_PUBLISHED",
          pinned_rule_set_version: null,
          resolved_rule_set_version: "1.0.0",
        },
        {
          project_id: "project-store-signage",
          project_name: "门店导视更新",
          policy: "PINNED",
          pinned_rule_set_version: "1.0.0",
          resolved_rule_set_version: "1.0.0",
        },
      ],
      compliance_artifacts: [
        {
          project_id: "project-summer-launch",
          project_name: "夏季新品发布",
          artifact_id: "artifact-brand-check",
          artifact_version_id: "artifact-version-brand-check-1",
          title: "夏季新品 KV · Candidate B",
          brand_rule_set_version: "1.0.0",
        },
      ],
    },
  };
}

export function getBrandKitBootstrap(): BrandKitBootstrap {
  const e2e =
    process.env.NODE_ENV !== "production" && process.env.LUMI_BRAND_KIT_E2E === "1";
  return e2e ? { mode: "e2e", seed: seed() } : { mode: "http", seed: null };
}
