"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { BrandColorToken, BrandRuleSeverity } from "@lumi/brand-rules";
import { useShell } from "@/components/app-shell/shell-context";
import { contrastRatio, draftPublishIssues, duplicateColorTokenIds, normalizeHexColor } from "@/lib/brand-kit/contracts";
import { getBrandKitGateway } from "@/lib/brand-kit/brand-kit-gateway";
import type {
  BrandComplianceResult,
  BrandFontAsset,
  BrandKitBootstrap,
  BrandKitDetail,
  BrandLogoAsset,
  BrandProjectBinding,
  BrandVisualAsset,
  FontRole,
  LogoBackground,
  LogoVariant,
  ReviewExtractionDecision,
  RightsAssertion,
  VisualReferencePolarity,
  VisualReferenceRole,
} from "@/lib/brand-kit/types";
import styles from "./brand-kit.module.css";

type Tab = "overview" | "assets" | "voice" | "guide" | "projects";

const TABS: readonly { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "assets", label: "Assets & Type" },
  { id: "voice", label: "Voice & Rules" },
  { id: "guide", label: "Brand Guide" },
  { id: "projects", label: "Projects & Compliance" },
];

function clone<T>(value: T): T {
  return structuredClone(value);
}

function uiError(error: unknown): string {
  return error instanceof Error ? error.message : "Brand Kit 操作失败，请重试。";
}

function splitList(value: string): readonly string[] {
  return value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean);
}

function joinList(value: readonly string[]): string {
  return value.join("，");
}

function nextColor(detail: BrandKitDetail): BrandColorToken {
  const index = detail.draft_token_set.colors.length + 1;
  return { id: `color-draft-${index}`, name: `Color ${index}`, value: "#808080", roles: ["accent"] };
}

export function BrandKitProduct({ bootstrap }: Readonly<{ bootstrap: BrandKitBootstrap }>) {
  const { activeOrganization, api, queryCache } = useShell();
  const gateway = useMemo(() => getBrandKitGateway(api, bootstrap), [api, bootstrap]);
  const [snapshot, setSnapshot] = useState<Awaited<ReturnType<typeof gateway.getBrandKit>> | null>(null);
  const [draft, setDraft] = useState<BrandKitDetail | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [rights, setRights] = useState<RightsAssertion>("USER_OWNED");
  const [uploadProgress, setUploadProgress] = useState<string | null>(null);
  const [guideDecisions, setGuideDecisions] = useState<Record<string, ReviewExtractionDecision>>( {} );
  const [compliance, setCompliance] = useState<BrandComplianceResult | null>(null);
  const [complianceVersion, setComplianceVersion] = useState<string>("");
  const [selectedArtifactVersion, setSelectedArtifactVersion] = useState<string>("");

  const applySnapshot = useCallback((next: Awaited<ReturnType<typeof gateway.getBrandKit>>) => {
    setSnapshot(next);
    setDraft(clone(next.detail));
    setDirty(false);
    setComplianceVersion(next.detail.published_versions.at(-1)?.version ?? "");
    setSelectedArtifactVersion(next.detail.compliance_artifacts[0]?.artifact_version_id ?? "");
  }, [gateway]);

  const load = useCallback(async () => {
    const next = await queryCache.fetchQuery(
      ["brand-kit", activeOrganization.id],
      (signal) => gateway.getBrandKit(activeOrganization.id, null, signal),
      0,
    );
    applySnapshot(next);
  }, [activeOrganization.id, applySnapshot, gateway, queryCache]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void load()
      .catch((loadError) => {
        if (!cancelled) setError(uiError(loadError));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [load]);

  const mutateDraft = (updater: (current: BrandKitDetail) => BrandKitDetail) => {
    setDraft((current) => current ? updater(current) : current);
    setDirty(true);
    setNotice(null);
  };

  const saveDraft = async () => {
    if (!draft || busy) return;
    setBusy(true);
    setError(null);
    try {
      const next = await gateway.saveDraft(activeOrganization.id, {
        brand_profile_id: draft.profile.id,
        expected_draft_revision: draft.draft_revision,
        name: draft.profile.name,
        token_set: draft.draft_token_set,
        rule_set: draft.draft_rule_set,
        logos: draft.logos,
        fonts: draft.fonts,
        visual_assets: draft.visual_assets,
      });
      applySnapshot(next);
      setNotice(`草稿已保存 · revision ${next.detail.draft_revision}`);
    } catch (saveError) {
      setError(uiError(saveError));
      queryCache.clear();
    } finally {
      setBusy(false);
    }
  };

  const publish = async () => {
    if (!draft || busy || dirty) return;
    const issues = draftPublishIssues(draft);
    if (issues.length) {
      setError(issues.join(" "));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await gateway.publishDraft(activeOrganization.id, {
        brand_profile_id: draft.profile.id,
        expected_draft_revision: draft.draft_revision,
      });
      applySnapshot(next);
      const version = next.detail.published_versions.at(-1)?.version ?? "unknown";
      setNotice(`BrandRuleSet v${version} 已发布。CURRENT 项目会在下一次 Run 启动时解析并冻结该版本。`);
    } catch (publishError) {
      setError(uiError(publishError));
    } finally {
      setBusy(false);
    }
  };

  const upload = async (
    file: File,
    kind: "LOGO" | "FONT" | "REFERENCE" | "GUIDE",
    options: { logoVariant?: LogoVariant; polarity?: VisualReferencePolarity; role?: VisualReferenceRole } = {},
  ) => {
    if (!draft || busy) return;
    setBusy(true);
    setError(null);
    setUploadProgress("准备上传…");
    try {
      const next = await gateway.uploadAsset(activeOrganization.id, {
        brand_profile_id: draft.profile.id,
        file,
        kind,
        rights_assertion: rights,
        ...(options.logoVariant ? { logo_variant: options.logoVariant } : {}),
        ...(options.polarity ? { reference_polarity: options.polarity } : {}),
        ...(options.role ? { reference_role: options.role } : {}),
        on_progress: (progress, state) => setUploadProgress(`${state} · ${progress}%`),
      });
      applySnapshot(next);
      setNotice(kind === "GUIDE" ? "Brand Guide 已进入提取审核队列；提取结果不会自动成为 Hard Rules。" : "资产已进入 Brand Kit。" );
    } catch (uploadError) {
      setError(uiError(uploadError));
    } finally {
      setBusy(false);
      setUploadProgress(null);
    }
  };

  if (loading) return <div className={styles.loading}>正在加载 Brand Kit…</div>;
  if (!snapshot || !draft) {
    return <div className={styles.loading} role="alert">{error ?? "无法加载 Brand Kit。"}</div>;
  }

  const publishIssues = draftPublishIssues(draft);
  const duplicateColors = new Set(duplicateColorTokenIds(draft.draft_token_set));
  const latestPublished = draft.published_versions.at(-1) ?? null;

  const updateColor = (id: string, patch: Partial<BrandColorToken>) => mutateDraft((current) => ({
    ...current,
    draft_token_set: {
      ...current.draft_token_set,
      colors: current.draft_token_set.colors.map((color) => color.id === id ? { ...color, ...patch } : color),
    },
  }));

  const updateLogo = (id: string, patch: Partial<BrandLogoAsset>) => mutateDraft((current) => ({
    ...current,
    logos: current.logos.map((logo) => logo.asset_id === id ? { ...logo, ...patch } : logo),
  }));

  const updateFontRole = (font: BrandFontAsset, role: FontRole) => mutateDraft((current) => ({
    ...current,
    fonts: current.fonts.map((item) => item.asset_id === font.asset_id ? { ...item, roles: [role] } : item),
    draft_token_set: {
      ...current.draft_token_set,
      fonts: current.draft_token_set.fonts.map((token) => token.asset_id === font.asset_id
        ? { ...token, roles: [role === "CJK_FALLBACK" ? "cjk_fallback" : role.toLowerCase()] }
        : token),
    },
  }));

  const overview = (
    <div className={styles.stack}>
      <section className={styles.heroCard}>
        <div>
          <span className={styles.eyebrow}>BRAND PROFILE</span>
          <input
            className={styles.brandName}
            aria-label="Brand name"
            value={draft.profile.name}
            onChange={(event) => mutateDraft((current) => ({ ...current, profile: { ...current.profile, name: event.currentTarget.value } }))}
          />
          <p>把 Logo、颜色、字体、语调、视觉参考和规则收敛成可执行的 BrandRuleSet，而不是提示词附件。</p>
        </div>
        <div className={styles.versionBlock}>
          <strong>{latestPublished ? `Published v${latestPublished.version}` : "Not published"}</strong>
          <span>Draft r{draft.draft_revision}</span>
          <span>{draft.draft_rule_set.version}</span>
        </div>
      </section>

      <section className={styles.sectionCard}>
        <div className={styles.sectionHeader}>
          <div><span className={styles.eyebrow}>COLOR TOKENS</span><h2>Palette</h2></div>
          <button type="button" onClick={() => mutateDraft((current) => ({
            ...current,
            draft_token_set: { ...current.draft_token_set, colors: [...current.draft_token_set.colors, nextColor(current)] },
          }))}>+ Add color</button>
        </div>
        <div className={styles.colorGrid}>
          {draft.draft_token_set.colors.map((color) => {
            const normalized = normalizeHexColor(color.value);
            const whiteContrast = contrastRatio(color.value, "#FFFFFF");
            const inkContrast = contrastRatio(color.value, "#1C1917");
            return (
              <article key={color.id} className={styles.colorCard} data-warning={duplicateColors.has(color.id)}>
                <div className={styles.swatch} style={{ background: normalized ?? "transparent" }} />
                <input aria-label={`${color.name} token name`} value={color.name} onChange={(event) => updateColor(color.id, { name: event.currentTarget.value })} />
                <input aria-label={`${color.name} HEX`} value={color.value} onChange={(event) => updateColor(color.id, { value: event.currentTarget.value })} />
                <input aria-label={`${color.name} roles`} value={joinList(color.roles)} onChange={(event) => updateColor(color.id, { roles: splitList(event.currentTarget.value) })} />
                <small>{normalized ?? "Invalid HEX"} · W {whiteContrast?.toFixed(1) ?? "—"}:1 · Ink {inkContrast?.toFixed(1) ?? "—"}:1</small>
                {duplicateColors.has(color.id) ? <strong>Duplicate color value</strong> : null}
              </article>
            );
          })}
        </div>
      </section>

      <section className={styles.previewGrid}>
        <article><span className={styles.eyebrow}>LOGOS</span><strong>{draft.logos.length}</strong><p>{draft.logos.filter((item) => item.scan_status === "READY").length} READY assets</p></article>
        <article><span className={styles.eyebrow}>TYPE</span><strong>{draft.fonts.length}</strong><p>{draft.fonts.filter((item) => item.rights_assertion !== "UNKNOWN").length} rights-known</p></article>
        <article><span className={styles.eyebrow}>RULES</span><strong>{draft.draft_rule_set.rules.filter((rule) => rule.active).length}</strong><p>{draft.draft_rule_set.rules.filter((rule) => rule.severity === "HARD" && rule.active).length} hard constraints</p></article>
        <article><span className={styles.eyebrow}>REFERENCES</span><strong>{draft.visual_assets.length}</strong><p>approved + negative direction</p></article>
      </section>
    </div>
  );

  const assets = (
    <div className={styles.stack}>
      <section className={styles.sectionCard}>
        <div className={styles.sectionHeader}>
          <div><span className={styles.eyebrow}>RIGHTS BOUNDARY</span><h2>Asset uploads</h2></div>
          <select aria-label="上传资产授权声明" value={rights} onChange={(event) => setRights(event.currentTarget.value as RightsAssertion)}>
            <option value="USER_OWNED">User owned</option><option value="LICENSED">Licensed</option><option value="UNKNOWN">Unknown rights</option>
          </select>
        </div>
        <p className={styles.help}>上传成功不等于获得商用授权。所有 Brand asset 继续经过 NODE-18 的校验、扫描和 rights metadata。</p>
        {uploadProgress ? <p className={styles.progress}>{uploadProgress}</p> : null}
      </section>

      <section className={styles.sectionCard}>
        <div className={styles.sectionHeader}>
          <div><span className={styles.eyebrow}>LOGO SYSTEM</span><h2>Logo variants</h2></div>
          <label className={styles.fileButton}>Upload logo<input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void upload(file, "LOGO", { logoVariant: "SECONDARY" }); event.currentTarget.value = ""; }} /></label>
        </div>
        <div className={styles.assetList}>
          {draft.logos.map((logo) => (
            <article key={logo.asset_id} className={styles.assetRow}>
              <div className={styles.assetPreview}>{logo.variant.slice(0, 2)}</div>
              <div className={styles.assetMeta}><strong>{logo.file_name}</strong><span>{logo.asset_id}</span><small>{logo.scan_status} · {logo.rights_assertion}</small></div>
              <label>Variant<select value={logo.variant} onChange={(event) => updateLogo(logo.asset_id, { variant: event.currentTarget.value as LogoVariant })}><option>PRIMARY</option><option>SECONDARY</option><option>MONOCHROME</option><option>ICON</option></select></label>
              <label>Background<select value={logo.preferred_background} onChange={(event) => updateLogo(logo.asset_id, { preferred_background: event.currentTarget.value as LogoBackground })}><option>LIGHT</option><option>DARK</option><option>ANY</option></select></label>
              <label>Min px<input type="number" min="1" value={logo.minimum_size_px} onChange={(event) => updateLogo(logo.asset_id, { minimum_size_px: Number(event.currentTarget.value) })} /></label>
              <label>Safe zone<input type="number" min="0" max="1" step="0.01" value={logo.safe_zone_ratio} onChange={(event) => updateLogo(logo.asset_id, { safe_zone_ratio: Number(event.currentTarget.value) })} /></label>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.sectionCard}>
        <div className={styles.sectionHeader}>
          <div><span className={styles.eyebrow}>TYPOGRAPHY</span><h2>Fonts & rights</h2></div>
          <label className={styles.fileButton}>Upload font<input type="file" accept=".woff,.woff2,.otf,.ttf" onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void upload(file, "FONT"); event.currentTarget.value = ""; }} /></label>
        </div>
        <div className={styles.fontPreview}>Aa 字体 Typography · 品牌风味 Brand voice · 0123456789</div>
        <div className={styles.assetList}>
          {draft.fonts.map((font) => (
            <article key={font.asset_id} className={styles.assetRow} data-warning={font.rights_assertion === "UNKNOWN"}>
              <div className={styles.assetPreview}>Aa</div>
              <div className={styles.assetMeta}><strong>{font.family}</strong><span>{font.file_name}</span><small>{font.scan_status} · {font.rights_assertion}</small>{font.license_note ? <small>{font.license_note}</small> : <small className={styles.warningText}>License unknown — cannot publish while this font is active.</small>}</div>
              <label>Role<select value={font.roles[0] ?? "BODY"} onChange={(event) => updateFontRole(font, event.currentTarget.value as FontRole)}><option value="HEADING">Heading</option><option value="BODY">Body</option><option value="CJK_FALLBACK">CJK fallback</option></select></label>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.sectionCard}>
        <div className={styles.sectionHeader}>
          <div><span className={styles.eyebrow}>VISUAL REFERENCES</span><h2>Approved / Negative</h2></div>
          <div className={styles.inlineActions}>
            <label className={styles.fileButton}>+ Approved<input type="file" accept="image/*" onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void upload(file, "REFERENCE", { polarity: "APPROVED", role: "PHOTOGRAPHY" }); event.currentTarget.value = ""; }} /></label>
            <label className={styles.fileButton}>+ Negative<input type="file" accept="image/*" onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void upload(file, "REFERENCE", { polarity: "NEGATIVE", role: "LAYOUT" }); event.currentTarget.value = ""; }} /></label>
          </div>
        </div>
        <div className={styles.referenceGrid}>
          {draft.visual_assets.map((reference) => (
            <article key={reference.asset_id} data-negative={reference.polarity === "NEGATIVE"}>
              <div className={styles.referencePreview}>{reference.polarity === "NEGATIVE" ? "AVOID" : "USE"}</div>
              <strong>{reference.file_name}</strong><span>{reference.role}</span><small>{reference.scan_status} · {reference.rights_assertion}</small>
            </article>
          ))}
        </div>
      </section>
    </div>
  );

  const updateVoice = (key: "tone_attributes" | "preferred_vocabulary" | "forbidden_terms" | "do_examples" | "dont_examples", value: string) => mutateDraft((current) => ({
    ...current,
    draft_rule_set: { ...current.draft_rule_set, voice: { ...current.draft_rule_set.voice, [key]: splitList(value) } },
  }));

  const voice = (
    <div className={styles.stack}>
      <section className={styles.sectionCard}>
        <div className={styles.sectionHeader}><div><span className={styles.eyebrow}>BRAND VOICE</span><h2>Language system</h2></div></div>
        <div className={styles.formGrid}>
          <label>Tone<input value={joinList(draft.draft_rule_set.voice.tone_attributes)} onChange={(event) => updateVoice("tone_attributes", event.currentTarget.value)} /></label>
          <label>Preferred vocabulary<input value={joinList(draft.draft_rule_set.voice.preferred_vocabulary)} onChange={(event) => updateVoice("preferred_vocabulary", event.currentTarget.value)} /></label>
          <label className={styles.full}>Forbidden words / claims<textarea value={joinList(draft.draft_rule_set.voice.forbidden_terms)} onChange={(event) => updateVoice("forbidden_terms", event.currentTarget.value)} /></label>
          <label className={styles.full}>Do<textarea value={joinList(draft.draft_rule_set.voice.do_examples ?? [])} onChange={(event) => updateVoice("do_examples", event.currentTarget.value)} /></label>
          <label className={styles.full}>Don’t<textarea value={joinList(draft.draft_rule_set.voice.dont_examples ?? [])} onChange={(event) => updateVoice("dont_examples", event.currentTarget.value)} /></label>
        </div>
      </section>
      <section className={styles.sectionCard}>
        <div className={styles.sectionHeader}><div><span className={styles.eyebrow}>EXECUTABLE RULES</span><h2>BrandRuleSet</h2></div><span className={styles.ruleVersion}>{draft.draft_rule_set.version}</span></div>
        <div className={styles.ruleList}>
          {draft.draft_rule_set.rules.map((rule) => (
            <article key={rule.id}>
              <div><strong>{rule.type}</strong><span>{rule.category} · {rule.source}</span><small>{rule.id}</small></div>
              <select aria-label={`${rule.id} severity`} value={rule.severity} onChange={(event) => mutateDraft((current) => ({ ...current, draft_rule_set: { ...current.draft_rule_set, rules: current.draft_rule_set.rules.map((item) => item.id === rule.id ? { ...item, severity: event.currentTarget.value as BrandRuleSeverity } : item) } }))} disabled={rule.source === "INFERRED_PROPOSAL"}>
                <option>HARD</option><option>SOFT</option><option>ADVISORY</option>
              </select>
              <label className={styles.switch}><input type="checkbox" checked={rule.active} onChange={(event) => mutateDraft((current) => ({ ...current, draft_rule_set: { ...current.draft_rule_set, rules: current.draft_rule_set.rules.map((item) => item.id === rule.id ? { ...item, active: event.currentTarget.checked } : item) } }))} />Active</label>
            </article>
          ))}
        </div>
      </section>
    </div>
  );

  const reviewProposal = async (proposalId: string) => {
    if (busy) return;
    const proposal = draft.guide_proposals.find((item) => item.id === proposalId);
    if (!proposal) return;
    const decisions = proposal.candidates.map((candidate) => guideDecisions[candidate.candidate_id]).filter((value): value is ReviewExtractionDecision => Boolean(value));
    if (decisions.length !== proposal.candidates.length) {
      setError("请逐条确认 Brand Guide 提取建议，不能把未审核候选直接发布为规则。" );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await gateway.reviewGuideProposal(activeOrganization.id, {
        brand_profile_id: draft.profile.id,
        proposal_id: proposal.id,
        expected_draft_revision: draft.draft_revision,
        decisions,
      });
      applySnapshot(next);
      setGuideDecisions({});
      setNotice("Brand Guide 提取建议已人工审核；批准项已转为 APPROVED_GUIDE_EXTRACTION。" );
    } catch (reviewError) {
      setError(uiError(reviewError));
    } finally {
      setBusy(false);
    }
  };

  const guide = (
    <div className={styles.stack}>
      <section className={styles.guideDrop}>
        <span className={styles.eyebrow}>PDF → PROPOSAL → HUMAN REVIEW → DRAFT → PUBLISH</span>
        <h2>Import Brand Guide</h2>
        <p>PDF 提取永远只是 proposal。每条候选必须保留 source citation，并经人工逐条确认；未经审核不能升级为 Hard Rule。</p>
        <label className={styles.primaryFile}>Choose PDF<input type="file" accept="application/pdf,.pdf" onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void upload(file, "GUIDE"); event.currentTarget.value = ""; }} /></label>
      </section>
      {draft.guide_proposals.length ? draft.guide_proposals.map((proposal) => (
        <section key={proposal.id} className={styles.sectionCard}>
          <div className={styles.sectionHeader}><div><span className={styles.eyebrow}>EXTRACTION PROPOSAL</span><h2>{proposal.id}</h2></div><strong className={styles.status}>{proposal.status}</strong></div>
          <p className={styles.help}>Source asset: {proposal.source_asset_id}{proposal.reviewed_by ? ` · reviewed by ${proposal.reviewed_by}` : ""}</p>
          <div className={styles.proposalList}>
            {proposal.candidates.map((candidate) => {
              const decision = guideDecisions[candidate.candidate_id];
              return (
                <article key={candidate.candidate_id}>
                  <div><strong>{candidate.rule.type}</strong><span>Confidence {(candidate.confidence * 100).toFixed(0)}% · proposed {candidate.rule.severity}</span>{candidate.citations.map((citation, index) => <small key={`${candidate.candidate_id}:${index}`}>Source · page {citation.page ?? "—"} · {citation.span ?? "exact citation"}</small>)}</div>
                  {proposal.status === "PROPOSED" ? <div className={styles.reviewControls}>
                    <select aria-label={`${candidate.candidate_id} review`} value={decision?.decision ?? ""} onChange={(event) => setGuideDecisions((current) => ({ ...current, [candidate.candidate_id]: { candidate_id: candidate.candidate_id, decision: event.currentTarget.value as "APPROVE" | "REJECT", severity: current[candidate.candidate_id]?.severity ?? candidate.rule.severity } }))}><option value="">Review…</option><option value="APPROVE">Approve</option><option value="REJECT">Reject</option></select>
                    <select aria-label={`${candidate.candidate_id} severity`} value={decision?.severity ?? candidate.rule.severity} disabled={decision?.decision !== "APPROVE"} onChange={(event) => setGuideDecisions((current) => ({ ...current, [candidate.candidate_id]: { candidate_id: candidate.candidate_id, decision: current[candidate.candidate_id]?.decision ?? "APPROVE", severity: event.currentTarget.value as BrandRuleSeverity } }))}><option>HARD</option><option>SOFT</option><option>ADVISORY</option></select>
                  </div> : null}
                </article>
              );
            })}
          </div>
          {proposal.status === "PROPOSED" ? <button type="button" className={styles.primary} disabled={busy} onClick={() => void reviewProposal(proposal.id)}>Apply human review</button> : null}
        </section>
      )) : <section className={styles.emptyCard}>还没有 Brand Guide extraction proposal。</section>}
    </div>
  );

  const updateBinding = async (binding: BrandProjectBinding, policy: BrandProjectBinding["policy"], pinned: string | null) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const next = await gateway.updateProjectBinding(activeOrganization.id, {
        brand_profile_id: draft.profile.id,
        project_id: binding.project_id,
        policy,
        pinned_rule_set_version: policy === "PINNED" ? pinned : null,
      });
      applySnapshot(next);
      setNotice(`${binding.project_name} 已更新 Brand binding。CURRENT 只在新 Run 开始时解析最新 Published 版本。`);
    } catch (bindingError) {
      setError(uiError(bindingError));
    } finally {
      setBusy(false);
    }
  };

  const runCompliance = async () => {
    if (!selectedArtifactVersion || !complianceVersion || busy) return;
    setBusy(true);
    setError(null);
    setCompliance(null);
    try {
      const result = await gateway.checkCompliance(activeOrganization.id, {
        brand_profile_id: draft.profile.id,
        artifact_version_id: selectedArtifactVersion,
        brand_rule_set_version: complianceVersion,
      });
      setCompliance(result);
    } catch (checkError) {
      setError(uiError(checkError));
    } finally {
      setBusy(false);
    }
  };

  const projects = (
    <div className={styles.stack}>
      <section className={styles.sectionCard}>
        <div className={styles.sectionHeader}><div><span className={styles.eyebrow}>PROJECT BINDING</span><h2>Current vs pinned</h2></div></div>
        <p className={styles.help}>CURRENT：每个新 Run 启动时解析当时最新 Published BrandRuleSet 并冻结；运行中不热更新。PINNED：始终使用指定历史版本。</p>
        <div className={styles.bindingList}>
          {draft.project_bindings.map((binding) => (
            <article key={binding.project_id}>
              <div><strong>{binding.project_name}</strong><span>{binding.project_id}</span><small>Resolved v{binding.resolved_rule_set_version ?? "—"}</small></div>
              <select aria-label={`${binding.project_name} binding policy`} value={binding.policy} onChange={(event) => void updateBinding(binding, event.currentTarget.value as BrandProjectBinding["policy"], binding.pinned_rule_set_version ?? latestPublished?.version ?? null)}><option value="CURRENT_PUBLISHED">Current published</option><option value="PINNED">Pinned</option></select>
              {binding.policy === "PINNED" ? <select aria-label={`${binding.project_name} pinned version`} value={binding.pinned_rule_set_version ?? ""} onChange={(event) => void updateBinding(binding, "PINNED", event.currentTarget.value)}>{draft.published_versions.map((version) => <option key={version.version} value={version.version}>v{version.version}</option>)}</select> : null}
            </article>
          ))}
        </div>
      </section>

      <section className={styles.sectionCard}>
        <div className={styles.sectionHeader}><div><span className={styles.eyebrow}>COMPLIANCE PREVIEW</span><h2>Check an exact ArtifactVersion</h2></div><button type="button" className={styles.primary} onClick={() => void runCompliance()} disabled={busy || !selectedArtifactVersion || !complianceVersion}>Run Brand check</button></div>
        <div className={styles.complianceControls}>
          <label>Artifact<select value={selectedArtifactVersion} onChange={(event) => setSelectedArtifactVersion(event.currentTarget.value)}>{draft.compliance_artifacts.map((artifact) => <option key={artifact.artifact_version_id} value={artifact.artifact_version_id}>{artifact.title} · {artifact.artifact_version_id}</option>)}</select></label>
          <label>Rule version<select value={complianceVersion} onChange={(event) => setComplianceVersion(event.currentTarget.value)}>{draft.published_versions.map((version) => <option key={version.version} value={version.version}>v{version.version}</option>)}<option value="0.0.0-stale">v0.0.0-stale · test stale guard</option></select></label>
        </div>
        {compliance ? <div className={styles.complianceResult}>
          <div className={styles.score}><strong>{compliance.report.score}</strong><span>{compliance.report.decision}</span><small>BrandRuleSet v{compliance.report.brand_rule_set_version}</small></div>
          <div className={styles.diagnosticList}>{compliance.report.diagnostics.map((diagnostic) => <article key={`${diagnostic.rule_id}:${diagnostic.node_id ?? "global"}`} data-severity={diagnostic.severity}><div><strong>{diagnostic.reason_code}</strong><span>{diagnostic.category} · {diagnostic.severity}</span><small>Rule {diagnostic.rule_id}{diagnostic.node_id ? ` · node ${diagnostic.node_id}` : ""}</small></div>{diagnostic.node_id ? <Link href={`/app/projects/${encodeURIComponent(compliance.project_id)}/workspace?focusNode=${encodeURIComponent(diagnostic.node_id)}&brandRuleVersion=${encodeURIComponent(compliance.report.brand_rule_set_version)}`}>在 Canvas 中定位 →</Link> : null}</article>)}</div>
        </div> : null}
      </section>
    </div>
  );

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div><span className={styles.eyebrow}>LUMI BRAND SYSTEM</span><h1>Brand Kit</h1><p>可执行、版本化、可审核的品牌系统。</p></div>
        <div className={styles.headerActions}>
          <span className={dirty ? styles.dirty : styles.saved}>{dirty ? "Unsaved draft" : `Draft r${draft.draft_revision} saved`}</span>
          <button type="button" onClick={() => void saveDraft()} disabled={busy || !dirty}>Save draft</button>
          <button type="button" className={styles.primary} onClick={() => void publish()} disabled={busy || dirty || publishIssues.length > 0}>Publish BrandRuleSet</button>
        </div>
      </header>
      <div className={styles.brandStrip}>
        <div><strong>{draft.profile.name}</strong><span>{latestPublished ? `Published v${latestPublished.version}` : "No published version"}</span></div>
        <div className={styles.brandPills}>{snapshot.brands.map((brand) => <span key={brand.id} data-active={brand.id === snapshot.active_brand_id}>{brand.name}</span>)}</div>
      </div>
      {error ? <div role="alert" className={styles.error}>{error}</div> : null}
      {notice ? <div role="status" className={styles.notice}>{notice}</div> : null}
      {publishIssues.length ? <details className={styles.publishIssues}><summary>{publishIssues.length} 个发布前检查未通过</summary>{publishIssues.map((issue) => <p key={issue}>{issue}</p>)}</details> : null}
      <nav className={styles.tabs} aria-label="Brand Kit sections">{TABS.map((item) => <button key={item.id} type="button" data-active={tab === item.id} onClick={() => setTab(item.id)}>{item.label}</button>)}</nav>
      <main className={styles.content}>
        {tab === "overview" ? overview : null}
        {tab === "assets" ? assets : null}
        {tab === "voice" ? voice : null}
        {tab === "guide" ? guide : null}
        {tab === "projects" ? projects : null}
      </main>
    </div>
  );
}
