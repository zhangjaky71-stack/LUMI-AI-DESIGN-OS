import {
  approveExtractionProposal,
  createExtractionProposal,
  rejectExtractionProposal,
  type BrandAssetSet,
  type BrandGuideExtractionProposal,
  type BrandRule,
  type BrandRuleSet,
  type BrandTokenSet,
} from "@lumi/brand-rules";
import { LumiApiClient } from "@/lib/app-shell/api-client";
import { brandKitProblem, draftPublishIssues, validateSaveDraftInput } from "./contracts";
import type {
  BrandComplianceInput,
  BrandComplianceResult,
  BrandFontAsset,
  BrandKitBootstrap,
  BrandKitDetail,
  BrandKitSnapshot,
  BrandLogoAsset,
  BrandVisualAsset,
  PublishBrandDraftInput,
  ReviewGuideProposalInput,
  SaveBrandDraftInput,
  UpdateBrandBindingInput,
  UploadBrandAssetInput,
} from "./types";

export interface BrandKitGateway {
  getBrandKit(organizationId: string, brandId?: string | null, signal?: AbortSignal): Promise<BrandKitSnapshot>;
  saveDraft(organizationId: string, input: SaveBrandDraftInput, signal?: AbortSignal): Promise<BrandKitSnapshot>;
  uploadAsset(organizationId: string, input: UploadBrandAssetInput, signal?: AbortSignal): Promise<BrandKitSnapshot>;
  reviewGuideProposal(
    organizationId: string,
    input: ReviewGuideProposalInput,
    signal?: AbortSignal,
  ): Promise<BrandKitSnapshot>;
  publishDraft(
    organizationId: string,
    input: PublishBrandDraftInput,
    signal?: AbortSignal,
  ): Promise<BrandKitSnapshot>;
  updateProjectBinding(
    organizationId: string,
    input: UpdateBrandBindingInput,
    signal?: AbortSignal,
  ): Promise<BrandKitSnapshot>;
  checkCompliance(
    organizationId: string,
    input: BrandComplianceInput,
    signal?: AbortSignal,
  ): Promise<BrandComplianceResult>;
}

interface UploadSessionResponse {
  readonly upload_id: string;
  readonly asset_id: string;
  readonly upload_url: string;
  readonly headers?: Readonly<Record<string, string>>;
}

interface UploadCompleteResponse {
  readonly asset_id: string;
  readonly scan_status: "QUEUED" | "SCANNING" | "READY" | "REJECTED";
  readonly failure_code?: string | null;
  readonly family?: string | null;
  readonly license_note?: string | null;
}

function request(signal?: AbortSignal): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

export class HttpBrandKitGateway implements BrandKitGateway {
  readonly #api: LumiApiClient;

  constructor(api: LumiApiClient) {
    this.#api = api;
  }

  getBrandKit(_organizationId: string, brandId?: string | null, signal?: AbortSignal) {
    const path = brandId
      ? `/brands/${encodeURIComponent(brandId)}/kit`
      : "/brands/active-kit";
    return this.#api.get<BrandKitSnapshot>(path, request(signal));
  }

  saveDraft(_organizationId: string, input: SaveBrandDraftInput, signal?: AbortSignal) {
    const safe = validateSaveDraftInput(input);
    return this.#api.patch<BrandKitSnapshot, Record<string, unknown>>(
      `/brands/${encodeURIComponent(safe.brand_profile_id)}/draft`,
      {
        name: safe.name,
        token_set: safe.token_set,
        rule_set: safe.rule_set,
        logos: safe.logos,
        fonts: safe.fonts,
        visual_assets: safe.visual_assets,
      },
      { if_match: String(safe.expected_draft_revision), ...request(signal) },
    );
  }

  async uploadAsset(_organizationId: string, input: UploadBrandAssetInput, signal?: AbortSignal) {
    input.on_progress?.(4, "UPLOADING");
    const session = await this.#api.post<UploadSessionResponse, Record<string, unknown>>(
      "/assets/uploads",
      {
        brand_profile_id: input.brand_profile_id,
        file_name: input.file.name,
        size_bytes: input.file.size,
        content_type: input.file.type || "application/octet-stream",
        asset_purpose: input.kind,
        rights_assertion: input.rights_assertion,
        logo_variant: input.logo_variant ?? null,
        reference_polarity: input.reference_polarity ?? null,
        reference_role: input.reference_role ?? null,
      },
      { idempotency_key: crypto.randomUUID(), ...request(signal) },
    );
    input.on_progress?.(18, "UPLOADING");
    await this.#api.putPresignedObject(session.upload_url, input.file, {
      headers: session.headers,
      content_type: input.file.type || "application/octet-stream",
      ...request(signal),
    });
    input.on_progress?.(82, "SCANNING");
    const completed = await this.#api.post<UploadCompleteResponse, Record<string, unknown>>(
      `/assets/uploads/${encodeURIComponent(session.upload_id)}/complete`,
      {
        asset_id: session.asset_id,
        brand_profile_id: input.brand_profile_id,
        asset_purpose: input.kind,
      },
      { idempotency_key: crypto.randomUUID(), ...request(signal) },
    );
    input.on_progress?.(
      100,
      completed.scan_status === "READY"
        ? "READY"
        : completed.scan_status === "REJECTED"
          ? "FAILED"
          : "SCANNING",
    );
    if (input.kind === "GUIDE" && completed.scan_status === "READY") {
      await this.#api.post<unknown, { source_asset_id: string }>(
        `/brands/${encodeURIComponent(input.brand_profile_id)}/guide-extractions`,
        { source_asset_id: completed.asset_id },
        { idempotency_key: crypto.randomUUID(), ...request(signal) },
      );
    }
    return this.getBrandKit(_organizationId, input.brand_profile_id, signal);
  }

  reviewGuideProposal(_organizationId: string, input: ReviewGuideProposalInput, signal?: AbortSignal) {
    return this.#api.post<BrandKitSnapshot, ReviewGuideProposalInput>(
      `/brands/${encodeURIComponent(input.brand_profile_id)}/guide-extractions/${encodeURIComponent(input.proposal_id)}/review`,
      input,
      { idempotency_key: crypto.randomUUID(), ...request(signal) },
    );
  }

  publishDraft(_organizationId: string, input: PublishBrandDraftInput, signal?: AbortSignal) {
    return this.#api.post<BrandKitSnapshot, PublishBrandDraftInput>(
      `/brands/${encodeURIComponent(input.brand_profile_id)}/publish`,
      input,
      { idempotency_key: crypto.randomUUID(), ...request(signal) },
    );
  }

  updateProjectBinding(_organizationId: string, input: UpdateBrandBindingInput, signal?: AbortSignal) {
    return this.#api.patch<BrandKitSnapshot, UpdateBrandBindingInput>(
      `/projects/${encodeURIComponent(input.project_id)}/brand-binding`,
      input,
      request(signal),
    );
  }

  checkCompliance(_organizationId: string, input: BrandComplianceInput, signal?: AbortSignal) {
    return this.#api.post<BrandComplianceResult, BrandComplianceInput>(
      `/artifact-versions/${encodeURIComponent(input.artifact_version_id)}/brand-compliance`,
      input,
      request(signal),
    );
  }
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function nextMajor(version: string | null): string {
  const major = version ? Number.parseInt(version.split(".")[0] ?? "0", 10) : 0;
  return `${Number.isFinite(major) ? major + 1 : 1}.0.0`;
}

function draftVersionAfter(publishedVersion: string): string {
  return `${nextMajor(publishedVersion)}-draft`;
}

function rebuildAssetSet(detail: BrandKitDetail): BrandAssetSet {
  return {
    ...detail.draft_asset_set,
    logo_asset_ids: detail.logos.filter((item) => item.scan_status === "READY").map((item) => item.asset_id),
    font_asset_ids: detail.fonts.filter((item) => item.scan_status === "READY").map((item) => item.asset_id),
    reference_asset_ids: detail.visual_assets
      .filter((item) => item.scan_status === "READY" && item.polarity === "APPROVED")
      .map((item) => item.asset_id),
    negative_reference_asset_ids: detail.visual_assets
      .filter((item) => item.scan_status === "READY" && item.polarity === "NEGATIVE")
      .map((item) => item.asset_id),
  };
}

export class DeterministicBrandKitGateway implements BrandKitGateway {
  #snapshot: BrandKitSnapshot;
  #counter = 40;

  constructor(seed: BrandKitSnapshot) {
    this.#snapshot = clone(seed);
  }

  async getBrandKit(organizationId: string, brandId?: string | null, signal?: AbortSignal) {
    this.#assertScope(organizationId, signal);
    if (brandId && brandId !== this.#snapshot.detail.profile.id) {
      throw brandKitProblem("BRAND_NOT_AVAILABLE_IN_FIXTURE", 404);
    }
    return clone(this.#snapshot);
  }

  async saveDraft(organizationId: string, input: SaveBrandDraftInput, signal?: AbortSignal) {
    this.#assertScope(organizationId, signal);
    const safe = validateSaveDraftInput(input);
    const detail = this.#requireDetail(safe.brand_profile_id, safe.expected_draft_revision);
    const nextDetail: BrandKitDetail = {
      ...detail,
      profile: { ...detail.profile, name: safe.name },
      draft_revision: detail.draft_revision + 1,
      draft_token_set: clone(safe.token_set),
      draft_rule_set: clone(safe.rule_set),
      logos: clone(safe.logos),
      fonts: clone(safe.fonts),
      visual_assets: clone(safe.visual_assets),
    };
    const withAssets = { ...nextDetail, draft_asset_set: rebuildAssetSet(nextDetail) };
    this.#replaceDetail(withAssets);
    return clone(this.#snapshot);
  }

  async uploadAsset(organizationId: string, input: UploadBrandAssetInput, signal?: AbortSignal) {
    this.#assertScope(organizationId, signal);
    const detail = this.#requireDetail(input.brand_profile_id);
    input.on_progress?.(12, "UPLOADING");
    await Promise.resolve();
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    input.on_progress?.(72, "SCANNING");
    await Promise.resolve();
    const rejected = /malware|scan-fail/i.test(input.file.name);
    const scanStatus = rejected ? "REJECTED" as const : "READY" as const;
    const assetId = `asset-brand-e2e-${++this.#counter}`;
    let nextDetail = detail;

    if (input.kind === "LOGO") {
      const asset: BrandLogoAsset = {
        asset_id: assetId,
        file_name: input.file.name,
        mime_type: input.file.type || "application/octet-stream",
        scan_status: scanStatus,
        rights_assertion: input.rights_assertion,
        variant: input.logo_variant ?? "SECONDARY",
        preferred_background: "ANY",
        minimum_size_px: 48,
        safe_zone_ratio: 0.16,
      };
      nextDetail = { ...nextDetail, logos: [...nextDetail.logos, asset] };
    } else if (input.kind === "FONT") {
      const family = input.file.name.replace(/\.(woff2?|otf|ttf)$/i, "") || "Uploaded font";
      const asset: BrandFontAsset = {
        asset_id: assetId,
        file_name: input.file.name,
        family,
        scan_status: scanStatus,
        rights_assertion: input.rights_assertion,
        license_note: input.rights_assertion === "UNKNOWN" ? null : "Rights assertion recorded by uploader.",
        roles: ["BODY"],
      };
      const tokenSet: BrandTokenSet = scanStatus === "READY"
        ? {
            ...nextDetail.draft_token_set,
            fonts: [
              ...nextDetail.draft_token_set.fonts,
              { id: `font-${assetId}`, name: family, asset_id: assetId, roles: ["body"] },
            ],
          }
        : nextDetail.draft_token_set;
      nextDetail = { ...nextDetail, fonts: [...nextDetail.fonts, asset], draft_token_set: tokenSet };
    } else if (input.kind === "REFERENCE") {
      const asset: BrandVisualAsset = {
        asset_id: assetId,
        file_name: input.file.name,
        mime_type: input.file.type || "application/octet-stream",
        scan_status: scanStatus,
        rights_assertion: input.rights_assertion,
        polarity: input.reference_polarity ?? "APPROVED",
        role: input.reference_role ?? "PHOTOGRAPHY",
      };
      nextDetail = { ...nextDetail, visual_assets: [...nextDetail.visual_assets, asset] };
      const visualAssets = [...nextDetail.visual_assets];
      nextDetail = {
        ...nextDetail,
        draft_rule_set: {
          ...nextDetail.draft_rule_set,
          visual_references: {
            ...nextDetail.draft_rule_set.visual_references,
            reference_asset_ids: visualAssets
              .filter((item) => item.scan_status === "READY" && item.polarity === "APPROVED")
              .map((item) => item.asset_id),
            negative_reference_asset_ids: visualAssets
              .filter((item) => item.scan_status === "READY" && item.polarity === "NEGATIVE")
              .map((item) => item.asset_id),
          },
        },
      };
    } else {
      if (!/pdf$/i.test(input.file.name) && input.file.type !== "application/pdf") {
        throw brandKitProblem("BRAND_GUIDE_MUST_BE_PDF", 400);
      }
      if (scanStatus === "READY") {
        const proposal = this.#guideProposal(nextDetail, assetId);
        nextDetail = { ...nextDetail, guide_proposals: [proposal, ...nextDetail.guide_proposals] };
      }
    }

    nextDetail = {
      ...nextDetail,
      draft_revision: nextDetail.draft_revision + 1,
      draft_asset_set: rebuildAssetSet(nextDetail),
    };
    this.#replaceDetail(nextDetail);
    input.on_progress?.(100, rejected ? "FAILED" : "READY");
    return clone(this.#snapshot);
  }

  async reviewGuideProposal(
    organizationId: string,
    input: ReviewGuideProposalInput,
    signal?: AbortSignal,
  ) {
    this.#assertScope(organizationId, signal);
    const detail = this.#requireDetail(input.brand_profile_id, input.expected_draft_revision);
    const proposal = detail.guide_proposals.find((item) => item.id === input.proposal_id);
    if (!proposal) throw brandKitProblem("GUIDE_PROPOSAL_NOT_FOUND", 404);
    const decisions = new Map(input.decisions.map((item) => [item.candidate_id, item]));
    if (proposal.candidates.some((candidate) => !decisions.has(candidate.candidate_id))) {
      throw brandKitProblem("GUIDE_REVIEW_INCOMPLETE", 400);
    }
    const approvals = input.decisions
      .filter((item) => item.decision === "APPROVE")
      .map((item) => ({
        candidate_id: item.candidate_id,
        ...(item.severity ? { severity: item.severity } : {}),
      }));
    let reviewed: BrandGuideExtractionProposal;
    let rules: readonly BrandRule[] = [];
    if (approvals.length) {
      const result = approveExtractionProposal(
        proposal,
        approvals,
        "user:e2e-brand-editor",
        "2026-08-15T04:20:00.000Z",
      );
      reviewed = result.proposal;
      rules = result.approved_rules;
    } else {
      reviewed = rejectExtractionProposal(
        proposal,
        "user:e2e-brand-editor",
        "2026-08-15T04:20:00.000Z",
      );
    }
    const nextDetail: BrandKitDetail = {
      ...detail,
      draft_revision: detail.draft_revision + 1,
      draft_rule_set: {
        ...detail.draft_rule_set,
        rules: [...detail.draft_rule_set.rules, ...rules],
      },
      guide_proposals: detail.guide_proposals.map((item) => item.id === reviewed.id ? reviewed : item),
    };
    this.#replaceDetail(nextDetail);
    return clone(this.#snapshot);
  }

  async publishDraft(organizationId: string, input: PublishBrandDraftInput, signal?: AbortSignal) {
    this.#assertScope(organizationId, signal);
    const detail = this.#requireDetail(input.brand_profile_id, input.expected_draft_revision);
    const issues = draftPublishIssues(detail);
    if (issues.length) throw brandKitProblem(`PUBLISH_BLOCKED_${issues.length}`, 422);
    const currentVersion = detail.published_versions.at(-1)?.version ?? null;
    const publishedVersion = nextMajor(currentVersion);
    const publishedAt = "2026-08-15T04:30:00.000Z";
    const tokenVersion = `tokens-${publishedVersion}`;
    const assetVersion = `assets-${publishedVersion}`;
    const published: BrandRuleSet = {
      ...detail.draft_rule_set,
      id: `brand-rules:${detail.profile.id}:${publishedVersion}`,
      version: publishedVersion,
      status: "PUBLISHED",
      token_set_version: tokenVersion,
      asset_set_version: assetVersion,
      created_at: detail.draft_rule_set.created_at,
      published_at: publishedAt,
    };
    const nextDraftVersion = draftVersionAfter(publishedVersion);
    const nextDraft: BrandRuleSet = {
      id: `brand-rules:${detail.profile.id}:${nextDraftVersion}`,
      organization_id: published.organization_id,
      brand_profile_id: published.brand_profile_id,
      version: nextDraftVersion,
      status: "DRAFT",
      token_set_version: `tokens-${nextDraftVersion}`,
      asset_set_version: `assets-${nextDraftVersion}`,
      rules: clone(published.rules),
      voice: clone(published.voice),
      visual_references: clone(published.visual_references),
      created_at: "2026-08-15T04:31:00.000Z",
    };
    const tokenSet: BrandTokenSet = {
      ...detail.draft_token_set,
      id: `brand-tokens:${detail.profile.id}:${nextDraftVersion}`,
      version: `tokens-${nextDraftVersion}`,
    };
    const assetSet: BrandAssetSet = {
      ...detail.draft_asset_set,
      id: `brand-assets:${detail.profile.id}:${nextDraftVersion}`,
      version: `assets-${nextDraftVersion}`,
    };
    const nextDetail: BrandKitDetail = {
      ...detail,
      draft_revision: detail.draft_revision + 1,
      draft_token_set: tokenSet,
      draft_asset_set: assetSet,
      draft_rule_set: nextDraft,
      published_versions: [...detail.published_versions, published],
      project_bindings: detail.project_bindings.map((binding) =>
        binding.policy === "CURRENT_PUBLISHED"
          ? { ...binding, resolved_rule_set_version: publishedVersion }
          : binding,
      ),
    };
    this.#replaceDetail(nextDetail, publishedVersion);
    return clone(this.#snapshot);
  }

  async updateProjectBinding(
    organizationId: string,
    input: UpdateBrandBindingInput,
    signal?: AbortSignal,
  ) {
    this.#assertScope(organizationId, signal);
    const detail = this.#requireDetail(input.brand_profile_id);
    const latest = detail.published_versions.at(-1)?.version ?? null;
    if (input.policy === "PINNED") {
      if (!input.pinned_rule_set_version) throw brandKitProblem("PINNED_VERSION_REQUIRED", 400);
      if (!detail.published_versions.some((item) => item.version === input.pinned_rule_set_version)) {
        throw brandKitProblem("BRAND_RULE_VERSION_STALE", 409);
      }
    }
    const nextDetail: BrandKitDetail = {
      ...detail,
      project_bindings: detail.project_bindings.map((binding) =>
        binding.project_id === input.project_id
          ? {
              ...binding,
              policy: input.policy,
              pinned_rule_set_version: input.policy === "PINNED" ? input.pinned_rule_set_version : null,
              resolved_rule_set_version: input.policy === "PINNED" ? input.pinned_rule_set_version : latest,
            }
          : binding,
      ),
    };
    this.#replaceDetail(nextDetail);
    return clone(this.#snapshot);
  }

  async checkCompliance(organizationId: string, input: BrandComplianceInput, signal?: AbortSignal) {
    this.#assertScope(organizationId, signal);
    const detail = this.#requireDetail(input.brand_profile_id);
    if (!detail.published_versions.some((item) => item.version === input.brand_rule_set_version)) {
      throw brandKitProblem("BRAND_RULE_VERSION_STALE", 409);
    }
    const artifact = detail.compliance_artifacts.find(
      (item) => item.artifact_version_id === input.artifact_version_id,
    );
    if (!artifact) throw brandKitProblem("ARTIFACT_VERSION_NOT_FOUND", 404);
    if (artifact.brand_rule_set_version !== input.brand_rule_set_version) {
      throw brandKitProblem("ARTIFACT_BRAND_VERSION_MISMATCH", 409);
    }
    return {
      project_id: artifact.project_id,
      artifact_version_id: artifact.artifact_version_id,
      report: {
        brand_rule_set_version: input.brand_rule_set_version,
        decision: "FAIL" as const,
        score: 78,
        hard_violation_count: 1,
        soft_violation_count: 1,
        advisory_count: 0,
        diagnostics: [
          {
            rule_id: "rule-color-allowed",
            severity: "HARD" as const,
            category: "COLOR" as const,
            reason_code: "FORBIDDEN_COLOR",
            node_id: "node-offer",
            expected: ["#1C1917", "#F3EBDD", "#D9A441"],
            actual: "#FF2D55",
            score: 0,
          },
          {
            rule_id: "rule-voice-terms",
            severity: "SOFT" as const,
            category: "VOICE" as const,
            reason_code: "FORBIDDEN_CLAIM",
            node_id: "node-headline",
            expected: "避免绝对化承诺",
            actual: "全网最低",
            score: 0.4,
          },
        ],
      },
    };
  }

  #guideProposal(detail: BrandKitDetail, sourceAssetId: string): BrandGuideExtractionProposal {
    return createExtractionProposal({
      id: `guide-proposal-${++this.#counter}`,
      organization_id: detail.profile.organization_id,
      brand_profile_id: detail.profile.id,
      source_asset_id: sourceAssetId,
      created_at: "2026-08-15T04:10:00.000Z",
      candidates: [
        {
          candidate_id: `guide-candidate-${this.#counter}-color`,
          confidence: 0.96,
          citations: [{ source_asset_id: sourceAssetId, page: 8, span: "Primary palette / Amber #D9A441" }],
          rule: {
            id: `rule-guide-${this.#counter}-color`,
            category: "COLOR",
            type: "ALLOWED_COLOR_TOKENS",
            severity: "SOFT",
            source: "INFERRED_PROPOSAL",
            priority: 70,
            scope: {},
            parameters: { token_ids: ["color-ink", "color-oat", "color-amber"] },
            active: true,
          },
        },
        {
          candidate_id: `guide-candidate-${this.#counter}-logo`,
          confidence: 0.91,
          citations: [{ source_asset_id: sourceAssetId, page: 12, span: "Clear space = 0.18× mark width" }],
          rule: {
            id: `rule-guide-${this.#counter}-logo`,
            category: "LOGO",
            type: "LOGO_CLEAR_SPACE",
            severity: "SOFT",
            source: "INFERRED_PROPOSAL",
            priority: 68,
            scope: { roles: ["logo"] },
            parameters: { clear_space_ratio: 0.18 },
            active: true,
          },
        },
        {
          candidate_id: `guide-candidate-${this.#counter}-voice`,
          confidence: 0.84,
          citations: [{ source_asset_id: sourceAssetId, page: 20, span: "Avoid superlative / unverifiable claims" }],
          rule: {
            id: `rule-guide-${this.#counter}-voice`,
            category: "VOICE",
            type: "VOICE_FORBIDDEN_TERMS",
            severity: "ADVISORY",
            source: "INFERRED_PROPOSAL",
            priority: 52,
            scope: { locales: ["zh-CN", "en"] },
            parameters: { terms: ["绝对最佳", "全网最低"] },
            active: true,
          },
        },
      ],
    });
  }

  #requireDetail(brandProfileId: string, revision?: number): BrandKitDetail {
    const detail = this.#snapshot.detail;
    if (detail.profile.id !== brandProfileId) throw brandKitProblem("BRAND_NOT_FOUND", 404);
    if (revision !== undefined && detail.draft_revision !== revision) {
      throw brandKitProblem("DRAFT_REVISION_CONFLICT", 409);
    }
    return detail;
  }

  #replaceDetail(detail: BrandKitDetail, publishedVersion?: string): void {
    this.#snapshot = {
      ...this.#snapshot,
      detail,
      brands: this.#snapshot.brands.map((brand) =>
        brand.id === detail.profile.id
          ? {
              ...brand,
              name: detail.profile.name,
              draft_revision: detail.draft_revision,
              published_version: publishedVersion ?? brand.published_version,
            }
          : brand,
      ),
    };
  }

  #assertScope(organizationId: string, signal?: AbortSignal): void {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (organizationId !== this.#snapshot.detail.profile.organization_id) {
      throw brandKitProblem("ORGANIZATION_FORBIDDEN", 403);
    }
  }
}

let deterministicGateway: DeterministicBrandKitGateway | null = null;
let deterministicKey = "";

export function getBrandKitGateway(api: LumiApiClient, bootstrap: BrandKitBootstrap): BrandKitGateway {
  if (bootstrap.mode !== "e2e") return new HttpBrandKitGateway(api);
  if (!bootstrap.seed) throw new Error("BRAND_KIT_E2E_SEED_REQUIRED");
  const key = `${bootstrap.seed.active_brand_id}:${bootstrap.seed.detail.draft_revision}`;
  if (!deterministicGateway || deterministicKey !== key) {
    deterministicGateway = new DeterministicBrandKitGateway(bootstrap.seed);
    deterministicKey = key;
  }
  return deterministicGateway;
}
