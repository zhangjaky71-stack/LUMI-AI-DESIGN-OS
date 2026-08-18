"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api/problem";
import {
  bindProjectBrand,
  createBrand,
  createBrandDraft,
  patchBrand,
  publishBrandRuleSet,
  publishGuideProposal,
  reviewGuideProposal,
} from "@/lib/brands/client";
import type {
  BrandAssetSet,
  BrandDraftInput,
  BrandGuideProposal,
  BrandRecord,
  BrandRule,
  BrandRuleSet,
  BrandTokenSet,
  BrandVisualStyle,
  BrandVoice,
} from "@/lib/brands/types";
import { newUuid7 } from "@/lib/canvas/uuid7";
import type { ProjectSummary } from "@/lib/projects/types";

type Section = "overview" | "palette" | "assets" | "voice" | "rules" | "guide" | "projects";

type EditorState = {
  tokenSet: BrandTokenSet;
  assetSet: BrandAssetSet;
  voice: BrandVoice;
  visualStyle: BrandVisualStyle;
  rulePolicy: ManagedRulePolicy;
  passthroughRules: readonly BrandRule[];
};

type ManagedRulePolicy = {
  allowedColorsEnabled: boolean;
  forbiddenColors: string;
  minimumContrast: string;
  fontFamilies: string;
  logoMinWidth: string;
  logoMinHeight: string;
  logoClearSpace: string;
  forbidLogoRotation: boolean;
  forbidLogoStretch: boolean;
  forbidLogoRecolor: boolean;
};

const MANAGED_KINDS = new Set([
  "ALLOWED_COLOR",
  "FORBIDDEN_COLOR",
  "MIN_CONTRAST",
  "FONT_ALLOWED",
  "LOGO_ALLOWED_ASSET",
  "LOGO_MIN_SIZE",
  "LOGO_CLEAR_SPACE",
  "LOGO_TRANSFORM",
]);

export function BrandStudio({
  organizationId,
  initialBrands,
  selectedBrand: initialSelectedBrand,
  activeRuleSet: initialRuleSet,
  initialProposal,
  initialProjects,
}: {
  organizationId: string;
  initialBrands: readonly BrandRecord[];
  selectedBrand: BrandRecord | null;
  activeRuleSet: BrandRuleSet | null;
  initialProposal: BrandGuideProposal | null;
  initialProjects: readonly ProjectSummary[];
}) {
  const router = useRouter();
  const [brands, setBrands] = useState<readonly BrandRecord[]>(initialBrands);
  const [selectedBrand, setSelectedBrand] = useState<BrandRecord | null>(initialSelectedBrand);
  const [ruleSet, setRuleSet] = useState<BrandRuleSet | null>(initialRuleSet);
  const [proposal, setProposal] = useState<BrandGuideProposal | null>(initialProposal);
  const [projects, setProjects] = useState<readonly ProjectSummary[]>(initialProjects);
  const [section, setSection] = useState<Section>("overview");
  const [editor, setEditor] = useState<EditorState>(() => editorFromRuleSet(initialRuleSet));
  const [brandName, setBrandName] = useState(initialSelectedBrand?.name ?? "");
  const [newBrandName, setNewBrandName] = useState("");
  const [proposalId, setProposalId] = useState(initialProposal?.id ?? "");
  const [pending, setPending] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setSelectedBrand(initialSelectedBrand);
    setRuleSet(initialRuleSet);
    setProposal(initialProposal);
    setEditor(editorFromRuleSet(initialRuleSet));
    setBrandName(initialSelectedBrand?.name ?? "");
    setProposalId(initialProposal?.id ?? "");
  }, [initialProposal, initialRuleSet, initialSelectedBrand]);

  const canEdit = selectedBrand !== null && pending === null;
  const paletteColors = useMemo(
    () => editor.tokenSet.tokens.filter((token) => looksLikeColor(token.value)),
    [editor.tokenSet.tokens],
  );
  const published = ruleSet?.status === "PUBLISHED";
  const draft = ruleSet?.status === "DRAFT";

  async function handleCreateBrand(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = newBrandName.trim();
    if (!name || pending) return;
    setPending("create-brand");
    setNotice(null);
    try {
      const created = await createBrand(organizationId, { name });
      setBrands((current) => [created, ...current]);
      setNewBrandName("");
      router.push(`/brands?brand=${encodeURIComponent(created.id)}`);
      router.refresh();
    } catch (error) {
      setNotice(userMessage(error, "Could not create the brand."));
    } finally {
      setPending(null);
    }
  }

  async function handleRenameBrand() {
    if (!selectedBrand || pending) return;
    const name = brandName.trim();
    if (!name || name === selectedBrand.name) return;
    setPending("rename-brand");
    setNotice(null);
    try {
      const updated = await patchBrand(organizationId, selectedBrand, { name });
      setSelectedBrand(updated);
      setBrands((current) => current.map((item) => item.id === updated.id ? updated : item));
      setNotice("Brand identity updated with version fencing.");
    } catch (error) {
      setNotice(userMessage(error, "The brand may have changed. Refresh before retrying."));
    } finally {
      setPending(null);
    }
  }

  async function handleSaveDraft() {
    if (!selectedBrand || pending) return;
    let input: BrandDraftInput;
    try {
      input = buildDraftInput(editor);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Brand draft is invalid.");
      return;
    }
    setPending("save-draft");
    setNotice(null);
    try {
      const created = await createBrandDraft(organizationId, selectedBrand.id, input);
      setRuleSet(created);
      setEditor(editorFromRuleSet(created));
      setNotice(`Draft v${created.version} created. Publishing is a separate explicit action.`);
    } catch (error) {
      setNotice(userMessage(error, "Could not create the brand draft."));
    } finally {
      setPending(null);
    }
  }

  async function handlePublish() {
    if (!selectedBrand || !ruleSet || ruleSet.status !== "DRAFT" || pending) return;
    setPending("publish");
    setNotice(null);
    try {
      const value = await publishBrandRuleSet(organizationId, selectedBrand.id, ruleSet.id);
      setRuleSet(value);
      setEditor(editorFromRuleSet(value));
      setNotice(`Published BrandRuleSet v${value.version}. Existing runs keep their frozen version.`);
      router.refresh();
    } catch (error) {
      setNotice(userMessage(error, "Publication was denied or the draft changed."));
    } finally {
      setPending(null);
    }
  }

  async function handleProposalReview(approve: boolean) {
    if (!selectedBrand || !proposal || proposal.status !== "PENDING_REVIEW" || pending) return;
    setPending(approve ? "approve-proposal" : "reject-proposal");
    setNotice(null);
    try {
      const reviewed = await reviewGuideProposal(organizationId, selectedBrand.id, proposal.id, approve);
      setProposal(reviewed);
      setNotice(approve ? "Guide proposal approved by a human reviewer. It is still not published." : "Guide proposal rejected. No rules were published.");
    } catch (error) {
      setNotice(userMessage(error, "Could not review this guide proposal."));
    } finally {
      setPending(null);
    }
  }

  async function handleProposalPublish() {
    if (!selectedBrand || !proposal || proposal.status !== "APPROVED" || pending) return;
    setPending("publish-proposal");
    setNotice(null);
    try {
      const value = await publishGuideProposal(organizationId, selectedBrand.id, proposal, ruleSet);
      setRuleSet(value);
      setEditor(editorFromRuleSet(value));
      setProposal({ ...proposal, status: "PUBLISHED" });
      setNotice(`Approved guide proposal published as BrandRuleSet v${value.version}.`);
      router.refresh();
    } catch (error) {
      setNotice(userMessage(error, "Guide proposal publication was denied."));
    } finally {
      setPending(null);
    }
  }

  async function handleBindProject(project: ProjectSummary, bind: boolean) {
    if (!selectedBrand || !project.version || pending) return;
    setPending(`project:${project.id}`);
    setNotice(null);
    try {
      const updated = await bindProjectBrand(organizationId, project.id, project.version, bind ? selectedBrand.id : null);
      setProjects((current) => current.map((item) => item.id === updated.id ? { ...item, version: updated.version, brandId: updated.brandId } : item));
      setNotice(bind ? `${project.name} now resolves this brand through the canonical Project binding.` : `${project.name} is no longer bound to this brand.`);
    } catch (error) {
      setNotice(userMessage(error, "Project binding changed. Refresh before retrying."));
    } finally {
      setPending(null);
    }
  }

  function openBrand(brandId: string) {
    router.push(`/brands?brand=${encodeURIComponent(brandId)}`);
  }

  function openProposal() {
    if (!selectedBrand || !proposalId.trim()) return;
    router.push(`/brands?brand=${encodeURIComponent(selectedBrand.id)}&proposal=${encodeURIComponent(proposalId.trim())}`);
  }

  return (
    <div className="brand-studio">
      <header className="brand-page-header">
        <div>
          <p className="eyebrow">Brand Intelligence</p>
          <h1>Brand Kit</h1>
          <p>Versioned brand truth for Agents, Canvas and compliance — never inferred rules published without review.</p>
        </div>
        {selectedBrand ? (
          <div className="brand-header-status">
            <span className={`brand-rule-status status-${(ruleSet?.status ?? "none").toLowerCase()}`}>{ruleSet ? `${ruleSet.status} · v${ruleSet.version}` : "No published rules"}</span>
            <button className="brand-secondary-button" type="button" onClick={handleSaveDraft} disabled={!canEdit || pending !== null}>{pending === "save-draft" ? "Creating draft…" : "Create new draft"}</button>
            {draft ? <button className="brand-primary-button" type="button" onClick={handlePublish} disabled={pending !== null}>{pending === "publish" ? "Publishing…" : "Publish draft"}</button> : null}
          </div>
        ) : null}
      </header>

      {notice ? <div className="brand-notice" role="status">{notice}</div> : null}

      <div className="brand-shell">
        <aside className="brand-list-panel">
          <div className="brand-list-heading"><span>Brands</span><strong>{brands.length}</strong></div>
          <div className="brand-list">
            {brands.map((brand) => (
              <button key={brand.id} type="button" className={selectedBrand?.id === brand.id ? "is-selected" : ""} onClick={() => openBrand(brand.id)}>
                <span className="brand-avatar">{brand.name.slice(0, 1).toUpperCase()}</span>
                <span><strong>{brand.name}</strong><small>{brand.activeRuleSetVersionId ? "Published rules" : "No active rules"}</small></span>
              </button>
            ))}
          </div>
          <form className="brand-create-form" onSubmit={handleCreateBrand}>
            <label><span>New brand</span><input value={newBrandName} onChange={(event) => setNewBrandName(event.target.value)} placeholder="Brand name" maxLength={200} /></label>
            <button type="submit" disabled={!newBrandName.trim() || pending !== null}>Create</button>
          </form>
        </aside>

        {selectedBrand ? (
          <main className="brand-main">
            <nav className="brand-section-tabs" aria-label="Brand Kit sections">
              {(["overview", "palette", "assets", "voice", "rules", "guide", "projects"] as const).map((value) => (
                <button key={value} type="button" className={section === value ? "is-active" : ""} onClick={() => setSection(value)}>{sectionLabel(value)}</button>
              ))}
            </nav>

            {section === "overview" ? <OverviewSection brand={selectedBrand} brandName={brandName} setBrandName={setBrandName} ruleSet={ruleSet} pending={pending} onRename={handleRenameBrand} /> : null}
            {section === "palette" ? <PaletteSection editor={editor} setEditor={setEditor} disabled={!canEdit} /> : null}
            {section === "assets" ? <AssetsSection editor={editor} setEditor={setEditor} disabled={!canEdit} /> : null}
            {section === "voice" ? <VoiceSection editor={editor} setEditor={setEditor} disabled={!canEdit} /> : null}
            {section === "rules" ? <RulesSection editor={editor} setEditor={setEditor} paletteColors={paletteColors.map((item) => item.value)} ruleSet={ruleSet} disabled={!canEdit} /> : null}
            {section === "guide" ? <GuideSection brand={selectedBrand} proposalId={proposalId} setProposalId={setProposalId} proposal={proposal} ruleSet={ruleSet} pending={pending} onOpen={openProposal} onReview={handleProposalReview} onPublish={handleProposalPublish} /> : null}
            {section === "projects" ? <ProjectsSection brand={selectedBrand} projects={projects} pending={pending} onBind={handleBindProject} /> : null}
          </main>
        ) : (
          <main className="brand-main brand-empty-state"><span className="brand-empty-mark">B</span><h2>Create your first Brand Kit</h2><p>A Brand exists independently from a RuleSet. After creation you can build a versioned draft and publish it explicitly.</p></main>
        )}
      </div>
    </div>
  );
}

function OverviewSection({ brand, brandName, setBrandName, ruleSet, pending, onRename }: { brand: BrandRecord; brandName: string; setBrandName: (value: string) => void; ruleSet: BrandRuleSet | null; pending: string | null; onRename: () => void }) {
  return (
    <section className="brand-content-grid">
      <article className="brand-card brand-card-wide">
        <div className="brand-card-heading"><div><p className="eyebrow">Identity</p><h2>Brand profile</h2></div><span>Brand v{brand.version}</span></div>
        <div className="brand-inline-editor"><label><span>Name</span><input value={brandName} maxLength={200} onChange={(event) => setBrandName(event.target.value)} /></label><button type="button" onClick={onRename} disabled={pending !== null || !brandName.trim() || brandName.trim() === brand.name}>Save name</button></div>
        <dl className="brand-meta-list"><div><dt>Brand ID</dt><dd><code>{brand.id}</code></dd></div><div><dt>Active RuleSet</dt><dd>{brand.activeRuleSetVersionId ? <code>{brand.activeRuleSetVersionId}</code> : "Not published"}</dd></div><div><dt>Updated</dt><dd>{formatDate(brand.updatedAt)}</dd></div></dl>
      </article>
      <MetricCard label="Palette tokens" value={ruleSet?.tokenSet.tokens.length ?? 0} detail="Versioned semantic tokens" />
      <MetricCard label="Allowed logos" value={ruleSet?.assetSet.allowedLogoAssetIds.length ?? 0} detail="Exact asset IDs" />
      <MetricCard label="Allowed fonts" value={ruleSet?.assetSet.allowedFontAssetIds.length ?? 0} detail="Publication checks rights" />
      <MetricCard label="Compliance rules" value={ruleSet?.rules.length ?? 0} detail={ruleSet ? `${ruleSet.status} snapshot ${ruleSet.snapshotHash.slice(0, 10)}…` : "Create a draft to begin"} />
      <article className="brand-card brand-card-wide">
        <div className="brand-card-heading"><div><p className="eyebrow">Version truth</p><h2>{ruleSet ? `${ruleSet.status} BrandRuleSet v${ruleSet.version}` : "No active BrandRuleSet"}</h2></div>{ruleSet ? <span>{ruleSet.source}</span> : null}</div>
        {ruleSet ? <><p className="brand-card-copy">Agents and compliance resolve this immutable snapshot. Draft changes do not affect existing runs until a new RuleSet is explicitly published.</p><dl className="brand-meta-list"><div><dt>RuleSet ID</dt><dd><code>{ruleSet.id}</code></dd></div><div><dt>Snapshot</dt><dd><code>{ruleSet.snapshotHash}</code></dd></div><div><dt>Published</dt><dd>{ruleSet.publishedAt ? formatDate(ruleSet.publishedAt) : "Draft only"}</dd></div></dl></> : <p className="brand-card-copy">The Brand registry exists, but no RuleSet is active. Use Create new draft, then Publish draft when the rule snapshot is ready.</p>}
      </article>
    </section>
  );
}

function PaletteSection({ editor, setEditor, disabled }: { editor: EditorState; setEditor: React.Dispatch<React.SetStateAction<EditorState>>; disabled: boolean }) {
  function updateToken(index: number, patch: { id?: string; value?: string; profile?: string }) {
    setEditor((current) => ({ ...current, tokenSet: { ...current.tokenSet, tokens: current.tokenSet.tokens.map((token, tokenIndex) => tokenIndex === index ? { ...token, ...patch } : token) } }));
  }
  return (
    <section className="brand-content-grid">
      <article className="brand-card brand-card-wide">
        <div className="brand-card-heading"><div><p className="eyebrow">Color system</p><h2>Palette tokens</h2></div><button type="button" className="brand-inline-action" disabled={disabled} onClick={() => setEditor((current) => ({ ...current, tokenSet: { ...current.tokenSet, tokens: [...current.tokenSet.tokens, { id: nextColorTokenId(current.tokenSet.tokens.map((item) => item.id)), value: "#111111", profile: "srgb" }] } }))}>+ Add token</button></div>
        <p className="brand-card-copy">Tokens are semantic brand values. Compliance color allowlists are managed separately under Rules, so changing a token never silently rewrites a hard rule.</p>
        <div className="palette-grid">
          {editor.tokenSet.tokens.map((token, index) => (
            <div className="palette-row" key={`${index}-${token.id}`}>
              <span className="palette-swatch" style={{ background: looksLikeColor(token.value) ? token.value : "transparent" }} />
              <label><span>Token</span><input value={token.id} disabled={disabled} onChange={(event) => updateToken(index, { id: event.target.value })} /></label>
              <label><span>Value</span><input value={token.value} disabled={disabled} onChange={(event) => updateToken(index, { value: event.target.value })} /></label>
              <label><span>Profile</span><input value={token.profile ?? ""} disabled={disabled} onChange={(event) => updateToken(index, { profile: event.target.value })} /></label>
              <button type="button" disabled={disabled} onClick={() => setEditor((current) => ({ ...current, tokenSet: { ...current.tokenSet, tokens: current.tokenSet.tokens.filter((_, tokenIndex) => tokenIndex !== index) } }))}>Remove</button>
            </div>
          ))}
          {!editor.tokenSet.tokens.length ? <div className="brand-empty-inline">No palette tokens yet.</div> : null}
        </div>
      </article>
    </section>
  );
}

function AssetsSection({ editor, setEditor, disabled }: { editor: EditorState; setEditor: React.Dispatch<React.SetStateAction<EditorState>>; disabled: boolean }) {
  return (
    <section className="brand-content-grid">
      <AssetIdCard title="Logo assets" description="Allowed logo variants. Publication uses exact Asset IDs." values={editor.assetSet.allowedLogoAssetIds} disabled={disabled} onChange={(values) => setEditor((current) => ({ ...current, assetSet: { ...current.assetSet, allowedLogoAssetIds: values } }))} />
      <AssetIdCard title="Font assets" description="Publication fails closed if a font is missing, not READY, not a font, or rights deny commercial use." values={editor.assetSet.allowedFontAssetIds} disabled={disabled} onChange={(values) => setEditor((current) => ({ ...current, assetSet: { ...current.assetSet, allowedFontAssetIds: values } }))} />
      <AssetIdCard title="Positive references" description="Approved visual references used by BrandContext." values={editor.assetSet.referenceAssetIds} disabled={disabled} onChange={(values) => setEditor((current) => ({ ...current, assetSet: { ...current.assetSet, referenceAssetIds: values } }))} />
      <AssetIdCard title="Negative references" description="Examples that should not be imitated." values={editor.assetSet.negativeReferenceAssetIds} disabled={disabled} onChange={(values) => setEditor((current) => ({ ...current, assetSet: { ...current.assetSet, negativeReferenceAssetIds: values } }))} />
      <article className="brand-card brand-card-wide brand-warning-card"><strong>Brand-scoped upload is not composed yet</strong><p>Current Asset upload endpoints require a Project storage scope. NODE-58 does not invent a direct URL upload path; existing READY Asset IDs can be attached here until the brand-scoped Asset lifecycle is implemented.</p></article>
    </section>
  );
}

function VoiceSection({ editor, setEditor, disabled }: { editor: EditorState; setEditor: React.Dispatch<React.SetStateAction<EditorState>>; disabled: boolean }) {
  const updateVoice = (field: keyof Omit<BrandVoice, "localeNotes">, value: string) => setEditor((current) => ({ ...current, voice: { ...current.voice, [field]: lines(value) } }));
  const updateVisual = (field: keyof BrandVisualStyle, value: string) => setEditor((current) => ({ ...current, visualStyle: { ...current.visualStyle, [field]: lines(value) } }));
  return (
    <section className="brand-content-grid">
      <TextListCard title="Tone attributes" value={editor.voice.toneAttributes} disabled={disabled} onChange={(value) => updateVoice("toneAttributes", value)} />
      <TextListCard title="Preferred vocabulary" value={editor.voice.preferredVocabulary} disabled={disabled} onChange={(value) => updateVoice("preferredVocabulary", value)} />
      <TextListCard title="Forbidden terms" value={editor.voice.forbiddenTerms} disabled={disabled} onChange={(value) => updateVoice("forbiddenTerms", value)} />
      <TextListCard title="Do examples" value={editor.voice.doExamples} disabled={disabled} onChange={(value) => updateVoice("doExamples", value)} />
      <TextListCard title="Don’t examples" value={editor.voice.dontExamples} disabled={disabled} onChange={(value) => updateVoice("dontExamples", value)} />
      <article className="brand-card brand-card-wide"><div className="brand-card-heading"><div><p className="eyebrow">Visual style</p><h2>Direction</h2></div></div><div className="brand-form-grid"><TextListField label="Photography" values={editor.visualStyle.photographyDirection} disabled={disabled} onChange={(value) => updateVisual("photographyDirection", value)} /><TextListField label="Lighting" values={editor.visualStyle.lighting} disabled={disabled} onChange={(value) => updateVisual("lighting", value)} /><TextListField label="Composition" values={editor.visualStyle.composition} disabled={disabled} onChange={(value) => updateVisual("composition", value)} /><TextListField label="Background" values={editor.visualStyle.backgroundStyle} disabled={disabled} onChange={(value) => updateVisual("backgroundStyle", value)} /><TextListField label="Texture" values={editor.visualStyle.texture} disabled={disabled} onChange={(value) => updateVisual("texture", value)} /><TextListField label="Illustration" values={editor.visualStyle.illustrationStyle} disabled={disabled} onChange={(value) => updateVisual("illustrationStyle", value)} /></div></article>
    </section>
  );
}

function RulesSection({ editor, setEditor, paletteColors, ruleSet, disabled }: { editor: EditorState; setEditor: React.Dispatch<React.SetStateAction<EditorState>>; paletteColors: readonly string[]; ruleSet: BrandRuleSet | null; disabled: boolean }) {
  const policy = editor.rulePolicy;
  const update = (patch: Partial<ManagedRulePolicy>) => setEditor((current) => ({ ...current, rulePolicy: { ...current.rulePolicy, ...patch } }));
  return (
    <section className="brand-content-grid">
      <article className="brand-card brand-card-wide"><div className="brand-card-heading"><div><p className="eyebrow">Compliance</p><h2>Managed rule policies</h2></div><span>{ruleSet?.rules.length ?? 0} current rules</span></div><p className="brand-card-copy">This UI writes only documented evaluator parameters. Existing rule kinds it does not manage are preserved unchanged in the next draft.</p><div className="brand-rule-form">
        <label className="brand-checkbox"><input type="checkbox" checked={policy.allowedColorsEnabled} disabled={disabled} onChange={(event) => update({ allowedColorsEnabled: event.target.checked })} /><span>Hard-allow current palette colors ({paletteColors.length})</span></label>
        <label><span>Forbidden colors · one per line</span><textarea value={policy.forbiddenColors} disabled={disabled} onChange={(event) => update({ forbiddenColors: event.target.value })} placeholder="#ff0000" /></label>
        <label><span>Minimum contrast ratio</span><input type="number" min="1" max="21" step="0.1" value={policy.minimumContrast} disabled={disabled} onChange={(event) => update({ minimumContrast: event.target.value })} /></label>
        <label><span>Allowed font families · one per line</span><textarea value={policy.fontFamilies} disabled={disabled} onChange={(event) => update({ fontFamilies: event.target.value })} /></label>
        <div className="brand-rule-numbers"><label><span>Logo min width</span><input type="number" min="0" value={policy.logoMinWidth} disabled={disabled} onChange={(event) => update({ logoMinWidth: event.target.value })} /></label><label><span>Logo min height</span><input type="number" min="0" value={policy.logoMinHeight} disabled={disabled} onChange={(event) => update({ logoMinHeight: event.target.value })} /></label><label><span>Logo clear space</span><input type="number" min="0" value={policy.logoClearSpace} disabled={disabled} onChange={(event) => update({ logoClearSpace: event.target.value })} /></label></div>
        <div className="brand-checkbox-row"><label className="brand-checkbox"><input type="checkbox" checked={policy.forbidLogoRotation} disabled={disabled} onChange={(event) => update({ forbidLogoRotation: event.target.checked })} /><span>Forbid logo rotation</span></label><label className="brand-checkbox"><input type="checkbox" checked={policy.forbidLogoStretch} disabled={disabled} onChange={(event) => update({ forbidLogoStretch: event.target.checked })} /><span>Forbid stretch</span></label><label className="brand-checkbox"><input type="checkbox" checked={policy.forbidLogoRecolor} disabled={disabled} onChange={(event) => update({ forbidLogoRecolor: event.target.checked })} /><span>Forbid recolor</span></label></div>
      </div></article>
      <article className="brand-card brand-card-wide"><div className="brand-card-heading"><div><p className="eyebrow">Preserved rules</p><h2>Other canonical rules</h2></div><span>{editor.passthroughRules.length}</span></div>{editor.passthroughRules.length ? <div className="brand-rule-list">{editor.passthroughRules.map((rule) => <div key={rule.id}><span className={`rule-severity severity-${rule.severity.toLowerCase()}`}>{rule.severity}</span><strong>{rule.key}</strong><small>{rule.kind} · {rule.source}</small></div>)}</div> : <p className="brand-card-copy">No unmanaged rules in the current snapshot.</p>}</article>
    </section>
  );
}

function GuideSection({ brand, proposalId, setProposalId, proposal, ruleSet, pending, onOpen, onReview, onPublish }: { brand: BrandRecord; proposalId: string; setProposalId: (value: string) => void; proposal: BrandGuideProposal | null; ruleSet: BrandRuleSet | null; pending: string | null; onOpen: () => void; onReview: (approve: boolean) => void; onPublish: () => void }) {
  return (
    <section className="brand-content-grid">
      <article className="brand-card brand-card-wide"><div className="brand-card-heading"><div><p className="eyebrow">Brand guide review</p><h2>Open cited proposal</h2></div></div><p className="brand-card-copy">Extraction/import service composition is still separate. This reviewer loads an exact proposal produced by the Brand Guide pipeline and never turns inferred rules into published hard rules automatically.</p><div className="brand-inline-editor"><label><span>Proposal ID</span><input value={proposalId} onChange={(event) => setProposalId(event.target.value)} placeholder="UUID" /></label><button type="button" onClick={onOpen} disabled={!proposalId.trim()}>Open proposal</button></div></article>
      {proposal ? <article className="brand-card brand-card-wide"><div className="brand-card-heading"><div><p className="eyebrow">Proposal</p><h2>{proposal.status}</h2></div><span>{proposal.rules.length} rules · {proposal.citations.length} citations</span></div><dl className="brand-meta-list"><div><dt>Source Asset</dt><dd><code>{proposal.sourceAssetId}</code></dd></div><div><dt>Proposal ID</dt><dd><code>{proposal.id}</code></dd></div><div><dt>Reviewed by</dt><dd>{proposal.reviewedBy ?? "Not reviewed"}</dd></div></dl><div className="guide-review-grid"><div><h3>Proposed rules</h3>{proposal.rules.map((rule) => <div className="guide-rule" key={rule.id}><span className={`rule-severity severity-${rule.severity.toLowerCase()}`}>{rule.severity}</span><strong>{rule.key}</strong><small>{rule.kind} · source {rule.source}</small><p>{rule.description ?? "No description"}</p></div>)}</div><div><h3>Source citations</h3>{proposal.citations.map((citation) => <div className="guide-citation" key={`${citation.pageNumber}:${citation.chunkRef}`}><strong>Page {citation.pageNumber}</strong><span>{citation.chunkRef}</span><code>{citation.evidenceHash.slice(0, 16)}…</code></div>)}</div></div><div className="guide-actions">{proposal.status === "PENDING_REVIEW" ? <><button type="button" className="brand-secondary-button" disabled={pending !== null} onClick={() => onReview(false)}>Reject proposal</button><button type="button" className="brand-primary-button" disabled={pending !== null} onClick={() => onReview(true)}>Approve proposal</button></> : null}{proposal.status === "APPROVED" ? <button type="button" className="brand-primary-button" disabled={pending !== null} onClick={onPublish}>{pending === "publish-proposal" ? "Publishing…" : `Publish approved proposal${ruleSet ? ` from v${ruleSet.version} context` : ""}`}</button> : null}{proposal.status === "PUBLISHED" ? <span className="brand-success-note">Published through reviewed guide path.</span> : null}</div></article> : null}
      <article className="brand-card brand-card-wide brand-warning-card"><strong>One-click “PDF → hard rules” is intentionally forbidden</strong><p>Every guide proposal must carry citations, remain `PENDING_REVIEW`, receive a human approve/reject decision, then publish through the reviewed path.</p></article>
    </section>
  );
}

function ProjectsSection({ brand, projects, pending, onBind }: { brand: BrandRecord; projects: readonly ProjectSummary[]; pending: string | null; onBind: (project: ProjectSummary, bind: boolean) => void }) {
  return (
    <section className="brand-content-grid"><article className="brand-card brand-card-wide"><div className="brand-card-heading"><div><p className="eyebrow">Project binding</p><h2>Projects using {brand.name}</h2></div><span>{projects.filter((project) => project.brandId === brand.id).length} bound</span></div><p className="brand-card-copy">Binding changes the canonical `Project.brand_id` using the Project resource version and If-Match. Agent runs resolve/freeze a Brand RuleSet downstream; this page does not rewrite historical runs.</p><div className="brand-project-list">{projects.map((project) => { const bound = project.brandId === brand.id; const boundElsewhere = Boolean(project.brandId && !bound); return <div key={project.id}><div><strong>{project.name}</strong><small>{bound ? "Bound to this brand" : boundElsewhere ? `Bound to ${shortId(project.brandId!)}` : "No brand"} · Project v{project.version ?? "?"}</small></div><button type="button" disabled={!project.version || pending !== null || boundElsewhere} onClick={() => onBind(project, !bound)}>{pending === `project:${project.id}` ? "Saving…" : bound ? "Unbind" : boundElsewhere ? "Bound elsewhere" : "Bind"}</button></div>; })}{!projects.length ? <div className="brand-empty-inline">No projects available.</div> : null}</div></article></section>
  );
}

function MetricCard({ label, value, detail }: { label: string; value: number; detail: string }) { return <article className="brand-card brand-metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>; }
function AssetIdCard({ title, description, values, disabled, onChange }: { title: string; description: string; values: readonly string[]; disabled: boolean; onChange: (values: readonly string[]) => void }) { return <article className="brand-card"><div className="brand-card-heading"><div><p className="eyebrow">Asset policy</p><h2>{title}</h2></div><span>{values.length}</span></div><p className="brand-card-copy">{description}</p><label className="brand-textarea-field"><span>Exact Asset IDs · one per line</span><textarea value={values.join("\n")} disabled={disabled} onChange={(event) => onChange(lines(event.target.value))} placeholder="asset UUID" /></label></article>; }
function TextListCard({ title, value, disabled, onChange }: { title: string; value: readonly string[]; disabled: boolean; onChange: (value: string) => void }) { return <article className="brand-card"><div className="brand-card-heading"><div><p className="eyebrow">Voice</p><h2>{title}</h2></div><span>{value.length}</span></div><label className="brand-textarea-field"><span>One item per line</span><textarea value={value.join("\n")} disabled={disabled} onChange={(event) => onChange(event.target.value)} /></label></article>; }
function TextListField({ label, values, disabled, onChange }: { label: string; values: readonly string[]; disabled: boolean; onChange: (value: string) => void }) { return <label className="brand-textarea-field"><span>{label}</span><textarea value={values.join("\n")} disabled={disabled} onChange={(event) => onChange(event.target.value)} /></label>; }

function editorFromRuleSet(ruleSet: BrandRuleSet | null): EditorState {
  const tokenSet = ruleSet ? { ...ruleSet.tokenSet, version: ruleSet.tokenSet.version + 1, tokens: ruleSet.tokenSet.tokens.map((item) => ({ ...item })) } : { id: newUuid7(), version: 1, tokens: [] };
  const assetSet = ruleSet ? { ...ruleSet.assetSet, version: ruleSet.assetSet.version + 1, allowedLogoAssetIds: [...ruleSet.assetSet.allowedLogoAssetIds], allowedFontAssetIds: [...ruleSet.assetSet.allowedFontAssetIds], referenceAssetIds: [...ruleSet.assetSet.referenceAssetIds], negativeReferenceAssetIds: [...ruleSet.assetSet.negativeReferenceAssetIds] } : { id: newUuid7(), version: 1, allowedLogoAssetIds: [], allowedFontAssetIds: [], referenceAssetIds: [], negativeReferenceAssetIds: [] };
  const rules = ruleSet?.rules ?? [];
  return {
    tokenSet,
    assetSet,
    voice: ruleSet ? cloneVoice(ruleSet.voice) : emptyVoice(),
    visualStyle: ruleSet ? cloneVisualStyle(ruleSet.visualStyle) : emptyVisualStyle(),
    rulePolicy: policyFromRules(rules),
    passthroughRules: rules.filter((rule) => !MANAGED_KINDS.has(rule.kind)),
  };
}

function buildDraftInput(editor: EditorState): BrandDraftInput {
  const tokenIds = editor.tokenSet.tokens.map((token) => token.id.trim());
  if (tokenIds.some((id) => !id)) throw new Error("Every brand token needs an ID.");
  if (new Set(tokenIds).size !== tokenIds.length) throw new Error("Brand token IDs must be unique.");
  const colors = editor.tokenSet.tokens.map((token) => token.value.trim()).filter(looksLikeColor);
  const managed = managedRules(editor.rulePolicy, colors, editor.assetSet);
  return {
    source: "USER_EXPLICIT",
    tokenSet: { ...editor.tokenSet, tokens: editor.tokenSet.tokens.map((token) => ({ ...token, id: token.id.trim(), value: token.value.trim(), profile: token.profile?.trim() || null })) },
    assetSet: { ...editor.assetSet, allowedLogoAssetIds: unique(editor.assetSet.allowedLogoAssetIds), allowedFontAssetIds: unique(editor.assetSet.allowedFontAssetIds), referenceAssetIds: unique(editor.assetSet.referenceAssetIds), negativeReferenceAssetIds: unique(editor.assetSet.negativeReferenceAssetIds) },
    rules: [...editor.passthroughRules, ...managed],
    voice: cloneVoice(editor.voice),
    visualStyle: cloneVisualStyle(editor.visualStyle),
  };
}

function managedRules(policy: ManagedRulePolicy, colors: readonly string[], assets: BrandAssetSet): BrandRule[] {
  const rules: BrandRule[] = [];
  const make = (kind: string, key: string, severity: BrandRule["severity"], parameters: Readonly<Record<string, unknown>>, description: string) => rules.push({ id: newUuid7(), key, kind, severity, source: "USER_EXPLICIT", parameters, description });
  if (policy.allowedColorsEnabled && colors.length) make("ALLOWED_COLOR", "palette.allowed", "HARD", { colors: unique(colors) }, "Only colors in the approved palette are allowed.");
  const forbidden = unique(lines(policy.forbiddenColors));
  if (forbidden.length) make("FORBIDDEN_COLOR", "palette.forbidden", "HARD", { colors: forbidden }, "Forbidden brand colors.");
  const contrast = positiveNumber(policy.minimumContrast);
  if (contrast !== null) make("MIN_CONTRAST", "accessibility.minimum-contrast", "SOFT", { ratio: contrast }, "Minimum contrast ratio for brand output.");
  const families = unique(lines(policy.fontFamilies));
  if (families.length || assets.allowedFontAssetIds.length) make("FONT_ALLOWED", "typography.allowed", "HARD", { families, asset_ids: unique(assets.allowedFontAssetIds) }, "Allowed brand fonts.");
  if (assets.allowedLogoAssetIds.length) make("LOGO_ALLOWED_ASSET", "logo.allowed-assets", "HARD", { asset_ids: unique(assets.allowedLogoAssetIds) }, "Only approved logo assets may be used.");
  const minWidth = nonNegativeNumber(policy.logoMinWidth); const minHeight = nonNegativeNumber(policy.logoMinHeight);
  if (minWidth !== null || minHeight !== null) make("LOGO_MIN_SIZE", "logo.minimum-size", "HARD", { min_width: minWidth ?? 0, min_height: minHeight ?? 0 }, "Minimum logo dimensions.");
  const clearSpace = nonNegativeNumber(policy.logoClearSpace);
  if (clearSpace !== null) make("LOGO_CLEAR_SPACE", "logo.clear-space", "HARD", { minimum: clearSpace }, "Minimum logo clear space.");
  if (policy.forbidLogoRotation || policy.forbidLogoStretch || policy.forbidLogoRecolor) make("LOGO_TRANSFORM", "logo.transforms", "HARD", { forbid_rotation: policy.forbidLogoRotation, forbid_stretch: policy.forbidLogoStretch, forbid_recolor: policy.forbidLogoRecolor }, "Logo transform restrictions.");
  return rules;
}

function policyFromRules(rules: readonly BrandRule[]): ManagedRulePolicy {
  const first = (kind: string) => rules.find((rule) => rule.kind === kind);
  const forbidden = first("FORBIDDEN_COLOR"); const contrast = first("MIN_CONTRAST"); const font = first("FONT_ALLOWED"); const size = first("LOGO_MIN_SIZE"); const clear = first("LOGO_CLEAR_SPACE"); const transform = first("LOGO_TRANSFORM");
  return {
    allowedColorsEnabled: Boolean(first("ALLOWED_COLOR")),
    forbiddenColors: parameterStrings(forbidden, "colors").join("\n"),
    minimumContrast: parameterNumber(contrast, "ratio"),
    fontFamilies: parameterStrings(font, "families").join("\n"),
    logoMinWidth: parameterNumber(size, "min_width"),
    logoMinHeight: parameterNumber(size, "min_height"),
    logoClearSpace: parameterNumber(clear, "minimum"),
    forbidLogoRotation: parameterBoolean(transform, "forbid_rotation", true),
    forbidLogoStretch: parameterBoolean(transform, "forbid_stretch", true),
    forbidLogoRecolor: parameterBoolean(transform, "forbid_recolor", true),
  };
}
function parameterStrings(rule: BrandRule | undefined, key: string): string[] { const value = rule?.parameters[key]; if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string"); return typeof value === "string" ? [value] : []; }
function parameterNumber(rule: BrandRule | undefined, key: string): string { const value = rule?.parameters[key]; return typeof value === "number" && Number.isFinite(value) ? String(value) : ""; }
function parameterBoolean(rule: BrandRule | undefined, key: string, fallback: boolean): boolean { const value = rule?.parameters[key]; return typeof value === "boolean" ? value : fallback; }
function emptyVoice(): BrandVoice { return { toneAttributes: [], preferredVocabulary: [], forbiddenTerms: [], doExamples: [], dontExamples: [], localeNotes: [] }; }
function emptyVisualStyle(): BrandVisualStyle { return { photographyDirection: [], lighting: [], composition: [], backgroundStyle: [], texture: [], illustrationStyle: [] }; }
function cloneVoice(value: BrandVoice): BrandVoice { return { toneAttributes: [...value.toneAttributes], preferredVocabulary: [...value.preferredVocabulary], forbiddenTerms: [...value.forbiddenTerms], doExamples: [...value.doExamples], dontExamples: [...value.dontExamples], localeNotes: value.localeNotes.map(([locale, note]) => [locale, note]) }; }
function cloneVisualStyle(value: BrandVisualStyle): BrandVisualStyle { return { photographyDirection: [...value.photographyDirection], lighting: [...value.lighting], composition: [...value.composition], backgroundStyle: [...value.backgroundStyle], texture: [...value.texture], illustrationStyle: [...value.illustrationStyle] }; }
function lines(value: string): string[] { return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean); }
function unique(values: readonly string[]): string[] { return [...new Set(values.map((item) => item.trim()).filter(Boolean))]; }
function looksLikeColor(value: string): boolean { return /^#[0-9a-f]{3,8}$/i.test(value.trim()) || /^(rgb|hsl)a?\(/i.test(value.trim()); }
function positiveNumber(value: string): number | null { if (!value.trim()) return null; const number = Number(value); if (!Number.isFinite(number) || number <= 0) throw new Error("Numeric brand rule values must be positive."); return number; }
function nonNegativeNumber(value: string): number | null { if (!value.trim()) return null; const number = Number(value); if (!Number.isFinite(number) || number < 0) throw new Error("Logo dimensions/clear space cannot be negative."); return number; }
function nextColorTokenId(ids: readonly string[]): string { const set = new Set(ids); let index = 1; while (set.has(`color.${index}`)) index += 1; return `color.${index}`; }
function sectionLabel(section: Section): string { if (section === "overview") return "Overview"; if (section === "palette") return "Palette"; if (section === "assets") return "Logos & Fonts"; if (section === "voice") return "Voice & Style"; if (section === "rules") return "Rules"; if (section === "guide") return "Guide Review"; return "Projects"; }
function userMessage(error: unknown, fallback: string): string { if (error instanceof ApiError) return error.detail || error.title || fallback; return error instanceof Error ? error.message : fallback; }
function formatDate(value: string): string { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date); }
function shortId(value: string): string { return value.length <= 14 ? value : `${value.slice(0, 6)}…${value.slice(-4)}`; }
