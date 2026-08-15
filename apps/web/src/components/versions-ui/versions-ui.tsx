"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { useShell } from "@/components/app-shell/shell-context";
import { getVersionsGateway } from "@/lib/versions-ui/versions-gateway";
import type {
  CompareViewMode,
  SafeVersionProvenance,
  VersionCompareResult,
  VersionPreview,
  VersionsBootstrap,
  VersionTimelineItem,
  VersionWorkspaceSnapshot,
} from "@/lib/versions-ui/types";
import styles from "./versions-ui.module.css";

function uiError(error: unknown): string {
  return error instanceof Error ? error.message : "Version history operation failed.";
}

function creatorLabel(item: VersionTimelineItem): string {
  const kind = item.version.created_by_type;
  return `${kind === "AGENT" ? "Agent" : kind === "USER" ? "User" : "System"} · ${item.version.created_by_id}`;
}

function timeLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function previewStyle(preview: VersionPreview): CSSProperties {
  return {
    "--background": preview.background,
    "--accent": preview.accent,
    "--secondary": preview.secondary,
  } as CSSProperties;
}

function PreviewArt({ preview }: Readonly<{ preview: VersionPreview }>) {
  return (
    <div
      className={styles.previewArt}
      style={previewStyle(preview)}
      aria-label={preview.label}
    />
  );
}

function branchHistory(
  snapshot: VersionWorkspaceSnapshot,
  branchId: string,
): readonly VersionTimelineItem[] {
  const branch = snapshot.branches.find((item) => item.id === branchId);
  if (!branch?.head_version_id) return [];
  const byId = new Map(snapshot.versions.map((item) => [item.version.id, item]));
  const rows: VersionTimelineItem[] = [];
  const seen = new Set<string>();
  let cursor: string | null = branch.head_version_id;
  while (cursor && !seen.has(cursor)) {
    seen.add(cursor);
    const item = byId.get(cursor);
    if (!item) break;
    rows.push(item);
    cursor = item.version.parent_version_id;
  }
  return rows;
}

function fact(label: string, value: string | number | null) {
  return (
    <div className={styles.fact}>
      <span>{label}</span>
      <span>{value == null || value === "" ? "—" : value}</span>
    </div>
  );
}

export function VersionsUI({
  projectId,
  bootstrap,
}: Readonly<{
  projectId: string;
  bootstrap: VersionsBootstrap;
}>) {
  const { activeOrganization, api, queryCache } = useShell();
  const gateway = useMemo(() => getVersionsGateway(api, bootstrap), [api, bootstrap]);
  const [snapshot, setSnapshot] = useState<VersionWorkspaceSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedBranchId, setSelectedBranchId] = useState<string | null>(null);
  const [compareFromId, setCompareFromId] = useState<string | null>(null);
  const [compareToId, setCompareToId] = useState<string | null>(null);
  const [compare, setCompare] = useState<VersionCompareResult | null>(null);
  const [compareMode, setCompareMode] = useState<CompareViewMode>("SIDE_BY_SIDE");
  const [wipe, setWipe] = useState(52);
  const [forkName, setForkName] = useState("dark-direction");
  const [restoreSourceId, setRestoreSourceId] = useState<string | null>(null);
  const [provenanceVersionId, setProvenanceVersionId] = useState<string | null>(null);
  const [provenance, setProvenance] = useState<SafeVersionProvenance | null>(null);
  const [provenanceError, setProvenanceError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void queryCache
      .fetchQuery(
        ["versions-ui", projectId],
        (signal) => gateway.getWorkspace(activeOrganization.id, projectId, null, signal),
        0,
      )
      .then((next) => {
        if (!cancelled) setSnapshot(next);
      })
      .catch((loadError) => {
        if (!cancelled) setError(uiError(loadError));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeOrganization.id, gateway, projectId, queryCache]);

  useEffect(() => {
    if (!snapshot) return;
    setSelectedBranchId((current) =>
      current && snapshot.branches.some((branch) => branch.id === current)
        ? current
        : snapshot.active_branch_id,
    );
    const ids = new Set(snapshot.versions.map((item) => item.version.id));
    const fallbackTo = snapshot.versions[0]?.version.id ?? null;
    const fallbackFrom = snapshot.versions[1]?.version.id ?? fallbackTo;
    setCompareToId((current) => (current && ids.has(current) ? current : fallbackTo));
    setCompareFromId((current) => (current && ids.has(current) ? current : fallbackFrom));
    setRestoreSourceId((current) => (current && ids.has(current) ? current : fallbackFrom));
    setProvenanceVersionId((current) => (current && ids.has(current) ? current : fallbackTo));
  }, [snapshot]);

  useEffect(() => {
    if (!snapshot || !compareFromId || !compareToId) {
      setCompare(null);
      return;
    }
    let cancelled = false;
    void gateway
      .compare(
        activeOrganization.id,
        snapshot.active_artifact.id,
        compareFromId,
        compareToId,
      )
      .then((next) => {
        if (!cancelled) setCompare(next);
      })
      .catch((compareError) => {
        if (!cancelled) setError(uiError(compareError));
      });
    return () => {
      cancelled = true;
    };
  }, [activeOrganization.id, compareFromId, compareToId, gateway, snapshot]);

  useEffect(() => {
    if (!snapshot || !provenanceVersionId) {
      setProvenance(null);
      return;
    }
    let cancelled = false;
    setProvenance(null);
    setProvenanceError(null);
    if (!snapshot.can_view_provenance) {
      setProvenanceError("PROVENANCE_FORBIDDEN");
      return;
    }
    void gateway
      .getProvenance(activeOrganization.id, provenanceVersionId)
      .then((next) => {
        if (!cancelled) setProvenance(next);
      })
      .catch((provenanceLoadError) => {
        if (!cancelled) setProvenanceError(uiError(provenanceLoadError));
      });
    return () => {
      cancelled = true;
    };
  }, [activeOrganization.id, gateway, provenanceVersionId, snapshot]);

  const switchArtifact = async (artifactId: string) => {
    if (!snapshot || artifactId === snapshot.active_artifact.id || busy) return;
    setBusy(true);
    setError(null);
    try {
      const next = await gateway.getWorkspace(activeOrganization.id, projectId, artifactId);
      setSnapshot(next);
      setSelectedBranchId(next.active_branch_id);
      setCompareFromId(null);
      setCompareToId(null);
      setRestoreSourceId(null);
      setProvenanceVersionId(null);
      setCompareMode("SIDE_BY_SIDE");
    } catch (switchError) {
      setError(uiError(switchError));
    } finally {
      setBusy(false);
    }
  };

  const checkUpdates = async () => {
    if (!snapshot || busy) return;
    const beforeFrom = compareFromId;
    const beforeTo = compareToId;
    setBusy(true);
    setError(null);
    try {
      const next = await gateway.checkForUpdates(
        activeOrganization.id,
        projectId,
        snapshot.active_artifact.id,
      );
      setSnapshot(next);
      const ids = new Set(next.versions.map((item) => item.version.id));
      if (beforeFrom && ids.has(beforeFrom)) setCompareFromId(beforeFrom);
      if (beforeTo && ids.has(beforeTo)) setCompareToId(beforeTo);
    } catch (updateError) {
      setError(uiError(updateError));
    } finally {
      setBusy(false);
    }
  };

  const restore = async () => {
    if (!snapshot || !restoreSourceId || !selectedBranchId || busy) return;
    const branch = snapshot.branches.find((item) => item.id === selectedBranchId);
    if (!branch) return;
    setBusy(true);
    setError(null);
    try {
      const next = await gateway.restore(activeOrganization.id, projectId, {
        artifact_id: snapshot.active_artifact.id,
        branch_id: branch.id,
        source_version_id: restoreSourceId,
        expected_head_version_id: branch.head_version_id,
      });
      setSnapshot(next);
      setSelectedBranchId(next.active_branch_id);
      setCompareToId(next.head_version_id);
      setProvenanceVersionId(next.head_version_id);
    } catch (restoreError) {
      setError(uiError(restoreError));
    } finally {
      setBusy(false);
    }
  };

  const fork = async () => {
    if (!snapshot || !compareToId || !forkName.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const next = await gateway.fork(activeOrganization.id, projectId, {
        artifact_id: snapshot.active_artifact.id,
        source_version_id: compareToId,
        name: forkName,
      });
      setSnapshot(next);
      setSelectedBranchId(next.active_branch_id);
      setForkName("");
    } catch (forkError) {
      setError(uiError(forkError));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div className={styles.loading}>正在加载不可变版本历史…</div>;
  if (!snapshot) {
    return (
      <div className={styles.loading} role="alert">
        <div>
          <p>{error ?? "Version history unavailable."}</p>
          <Link href={`/app/projects/${encodeURIComponent(projectId)}`}>返回项目</Link>
        </div>
      </div>
    );
  }

  const selectedBranch =
    snapshot.branches.find((branch) => branch.id === selectedBranchId) ?? snapshot.branches[0];
  const timeline = selectedBranch
    ? branchHistory(snapshot, selectedBranch.id)
    : snapshot.versions;
  const versionById = new Map(snapshot.versions.map((item) => [item.version.id, item]));
  const restoreSource = restoreSourceId ? versionById.get(restoreSourceId) ?? null : null;
  const provenanceItem = provenanceVersionId
    ? versionById.get(provenanceVersionId) ?? null
    : null;

  const preview = (item: VersionTimelineItem, label: string) => (
    <div className={styles.previewCard}>
      <div className={styles.previewLabel}>
        <strong>
          {label} · v{item.version.version_number}
        </strong>
        <span>
          {item.version.id} · {item.preview.label}
        </span>
      </div>
      <PreviewArt preview={item.preview} />
    </div>
  );

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerTitle}>
          <div>
            <Link href={`/app/projects/${encodeURIComponent(projectId)}/workspace`}>
              ← AI Workspace
            </Link>
            <span className={styles.eyebrow}>ARTIFACT HISTORY · NODE-42 CANONICAL</span>
            <h1>{snapshot.project_name} · Versions</h1>
          </div>
        </div>
        <div className={styles.headerActions}>
          <select
            className={styles.select}
            aria-label="Artifact"
            value={snapshot.active_artifact.id}
            onChange={(event) => void switchArtifact(event.target.value)}
            disabled={busy}
          >
            {snapshot.artifact_options.map((artifact) => (
              <option key={artifact.artifact_id} value={artifact.artifact_id}>
                {artifact.title} · {artifact.type} · {artifact.version_count} versions
              </option>
            ))}
          </select>
          <button
            className={styles.button}
            type="button"
            onClick={() => void checkUpdates()}
            disabled={busy}
          >
            检查更新
          </button>
          <Link href={`/app/projects/${encodeURIComponent(projectId)}`} className={styles.button}>
            Project Brief
          </Link>
        </div>
      </header>

      {snapshot.notice ? (
        <div className={styles.notice} role="status">
          {snapshot.notice.message}
        </div>
      ) : null}
      {error ? (
        <div className={styles.error} role="alert">
          {error}
        </div>
      ) : null}

      <main className={styles.shell}>
        <aside className={styles.panel} aria-label="Version timeline">
          <div className={styles.panelHeader}>
            <div>
              <span className={styles.eyebrow}>TIMELINE</span>
              <h2>Version history</h2>
            </div>
            <small>rev {snapshot.revision}</small>
          </div>
          <div className={styles.branchBar}>
            <label>
              Branch
              <select
                className={styles.select}
                aria-label="Branch"
                value={selectedBranch?.id ?? ""}
                onChange={(event) => setSelectedBranchId(event.target.value)}
              >
                {snapshot.branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name}
                  </option>
                ))}
              </select>
            </label>
            <div className={styles.breadcrumb}>
              {selectedBranch?.name ?? "branch"} ← {selectedBranch?.base_version_id ?? "root"} · head{" "}
              {selectedBranch?.head_version_id ?? "empty"}
            </div>
          </div>

          <div className={styles.timeline}>
            {timeline.map((item) => (
              <article
                key={item.version.id}
                className={styles.versionCard}
                data-head={selectedBranch?.head_version_id === item.version.id}
              >
                <div className={styles.miniPreview} style={previewStyle(item.preview)} />
                <div className={styles.versionMeta}>
                  <div className={styles.versionTop}>
                    <strong>v{item.version.version_number}</strong>
                    <span className={styles.badge} data-status={item.version.status}>
                      {item.version.status}
                    </span>
                    <span className={styles.badge}>
                      {item.quality.score == null ? item.quality.label : `Q ${item.quality.score}`}
                    </span>
                    {selectedBranch?.head_version_id === item.version.id ? (
                      <span className={styles.badge}>HEAD</span>
                    ) : null}
                  </div>
                  <p>{item.safe_change_summary}</p>
                  <small>
                    {creatorLabel(item)} · {item.branch_name} · {timeLabel(item.version.created_at)}
                  </small>
                </div>
                <div className={styles.cardActions}>
                  <button type="button" onClick={() => setCompareFromId(item.version.id)}>
                    设为 Before
                  </button>
                  <button type="button" onClick={() => setCompareToId(item.version.id)}>
                    设为 After
                  </button>
                  <button type="button" onClick={() => setRestoreSourceId(item.version.id)}>
                    恢复此版本
                  </button>
                  <button type="button" onClick={() => setProvenanceVersionId(item.version.id)}>
                    Provenance
                  </button>
                </div>
              </article>
            ))}
          </div>

          <div className={styles.actionBox}>
            <h4>Restore</h4>
            <p>恢复会创建一个新的 DRAFT 版本，不删除后来历史，也不会把 branch head 回拨。</p>
            <div className={styles.actionRow}>
              <select
                className={styles.select}
                aria-label="Restore source"
                value={restoreSourceId ?? ""}
                onChange={(event) => setRestoreSourceId(event.target.value)}
              >
                {snapshot.versions.map((item) => (
                  <option key={item.version.id} value={item.version.id}>
                    v{item.version.version_number} · {item.version.status}
                  </option>
                ))}
              </select>
              <button
                className={styles.primary}
                type="button"
                onClick={() => void restore()}
                disabled={!restoreSource || busy}
              >
                创建恢复版本
              </button>
            </div>
          </div>

          <div className={styles.actionBox}>
            <h4>Fork from After</h4>
            <p>从当前 After 版本创建独立分支。P0 不提供复杂 merge UI。</p>
            <div className={styles.actionRow}>
              <input
                className={styles.input}
                aria-label="New branch name"
                value={forkName}
                onChange={(event) => setForkName(event.target.value)}
                placeholder="dark-direction"
              />
              <button
                className={styles.button}
                type="button"
                onClick={() => void fork()}
                disabled={!forkName.trim() || !compareToId || busy}
              >
                Fork
              </button>
            </div>
          </div>
        </aside>

        <section className={`${styles.panel} ${styles.comparePanel}`} aria-label="Version compare">
          <div className={styles.compareToolbar}>
            <div className={styles.versionPickers}>
              <select
                className={styles.select}
                aria-label="Compare before"
                value={compareFromId ?? ""}
                onChange={(event) => setCompareFromId(event.target.value)}
              >
                {snapshot.versions.map((item) => (
                  <option key={item.version.id} value={item.version.id}>
                    Before · v{item.version.version_number} · {item.version.id}
                  </option>
                ))}
              </select>
              <span>→ exact compare →</span>
              <select
                className={styles.select}
                aria-label="Compare after"
                value={compareToId ?? ""}
                onChange={(event) => setCompareToId(event.target.value)}
              >
                {snapshot.versions.map((item) => (
                  <option key={item.version.id} value={item.version.id}>
                    After · v{item.version.version_number} · {item.version.id}
                  </option>
                ))}
              </select>
            </div>
            <div className={styles.segment} aria-label="Compare mode">
              <button
                type="button"
                data-active={compareMode === "SIDE_BY_SIDE"}
                onClick={() => setCompareMode("SIDE_BY_SIDE")}
              >
                Side-by-side
              </button>
              <button
                type="button"
                data-active={compareMode === "OVERLAY"}
                onClick={() => setCompareMode("OVERLAY")}
              >
                Overlay
              </button>
              <button
                type="button"
                data-active={compareMode === "WIPE"}
                onClick={() => setCompareMode("WIPE")}
              >
                Wipe
              </button>
            </div>
          </div>

          <div className={styles.compareBody}>
            {compare ? (
              <>
                {compareMode === "SIDE_BY_SIDE" ? (
                  <div className={styles.previewGrid}>
                    {preview(compare.before, "Before")}
                    {preview(compare.after, "After")}
                  </div>
                ) : compareMode === "OVERLAY" ? (
                  <div className={styles.overlayWrap} aria-label="Overlay compare">
                    <div className={styles.overlayLayer}>
                      <PreviewArt preview={compare.before.preview} />
                    </div>
                    <div className={styles.overlayLayer} data-top="true">
                      <PreviewArt preview={compare.after.preview} />
                    </div>
                  </div>
                ) : (
                  <>
                    <div className={styles.wipeWrap} aria-label="Wipe compare">
                      <div className={styles.wipeLayer}>
                        <PreviewArt preview={compare.before.preview} />
                      </div>
                      <div
                        className={styles.wipeLayer}
                        data-top="true"
                        style={{ "--wipe": `${wipe}%` } as CSSProperties}
                      >
                        <PreviewArt preview={compare.after.preview} />
                      </div>
                    </div>
                    <label className={styles.wipeControl}>
                      Before
                      <input
                        aria-label="Wipe position"
                        type="range"
                        min="0"
                        max="100"
                        value={wipe}
                        onChange={(event) => setWipe(Number(event.target.value))}
                      />
                      After · {wipe}%
                    </label>
                  </>
                )}

                <div className={styles.changes}>
                  <div className={styles.changesHeader}>
                    <strong>Semantic diff</strong>
                    <span>
                      {compare.semantic_changes.length} structured changes · {compare.from_version_id} →{" "}
                      {compare.to_version_id}
                    </span>
                  </div>
                  {compare.semantic_changes.length ? (
                    compare.semantic_changes.map((change) => (
                      <div className={styles.changeRow} key={change.id}>
                        <span className={styles.changeKind}>{change.kind}</span>
                        <strong>
                          {change.node_name ?? "Artifact"} · {change.property}
                        </strong>
                        <span className={styles.changeValues}>
                          {String(change.before ?? "∅")} → {String(change.after ?? "∅")}
                          {change.protected_identity ? " · protected identity" : ""}
                        </span>
                      </div>
                    ))
                  ) : (
                    <div className={styles.changeRow}>
                      <span className={styles.changeKind}>NO CHANGE</span>
                      <strong>Same exact version</strong>
                      <span className={styles.changeValues}>No semantic delta.</span>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className={styles.provenanceEmpty}>
                选择两个精确 ArtifactVersion 进行比较。
              </div>
            )}
          </div>
        </section>

        <aside className={`${styles.panel} ${styles.provenancePanel}`} aria-label="Version provenance">
          <div className={styles.panelHeader}>
            <div>
              <span className={styles.eyebrow}>TRACEABILITY</span>
              <h3>Provenance</h3>
            </div>
            <small>{provenanceItem ? `v${provenanceItem.version.version_number}` : "—"}</small>
          </div>
          <div className={styles.provenanceBody}>
            {!snapshot.can_view_provenance || provenanceError ? (
              <div className={styles.provenanceEmpty} role="status">
                Provenance access is restricted for this project. Raw prompts, system prompts, tool payloads
                and private reasoning are never exposed here.
                {provenanceError ? (
                  <>
                    <br />
                    <code>{provenanceError}</code>
                  </>
                ) : null}
              </div>
            ) : provenance ? (
              <>
                <div className={styles.provenanceGroup}>
                  <h4>Creation</h4>
                  {fact("Created by", `${provenance.created_by_type} · ${provenance.created_by_id}`)}
                  {fact("Agent run", provenance.agent_run_id)}
                  {fact("Task", provenance.task_id)}
                  {fact("Model", provenance.model)}
                  {fact("Provider", provenance.provider)}
                  {fact("Recipe", provenance.recipe_version)}
                </div>
                <div className={styles.provenanceGroup}>
                  <h4>Governance</h4>
                  {fact("Brand rules", provenance.brand_rule_set_version)}
                  {fact("Quality", provenanceItem?.quality.label ?? null)}
                  {fact("Approval", provenanceItem?.approval.status ?? null)}
                  {provenance.quality_checks.map((check) => (
                    <div className={styles.fact} key={check}>
                      <span>Check</span>
                      <span>{check}</span>
                    </div>
                  ))}
                </div>
                <div className={styles.provenanceGroup}>
                  <h4>Safe prompt identity</h4>
                  {fact("Template", provenance.prompt_template_version)}
                  <div className={styles.fact}>
                    <span>Prompt hash</span>
                    <code>{provenance.prompt_hash ?? "—"}</code>
                  </div>
                  <div className={styles.fact}>
                    <span>Constraint hash</span>
                    <code>{provenance.constraint_snapshot_hash}</code>
                  </div>
                  <p className={styles.hash}>
                    Only safe summaries/hashes are shown. No raw system prompt or chain-of-thought.
                  </p>
                </div>
                <div className={styles.provenanceGroup}>
                  <h4>Compiler & inputs</h4>
                  {fact("Compiler", provenance.compiler?.compiler_version ?? null)}
                  {fact("Document", provenance.compiler?.document_id ?? null)}
                  {fact("Compile hash", provenance.compiler?.compile_hash ?? null)}
                  {fact("Git SHA", provenance.code_git_sha)}
                  {provenance.input_asset_ids.map((id) => (
                    <div className={styles.fact} key={id}>
                      <span>Asset</span>
                      <code>{id}</code>
                    </div>
                  ))}
                  {provenance.input_artifact_version_ids.map((id) => (
                    <div className={styles.fact} key={id}>
                      <span>ArtifactVersion</span>
                      <code>{id}</code>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className={styles.provenanceEmpty}>
                正在读取安全 Provenance projection…
              </div>
            )}
          </div>
        </aside>
      </main>
    </div>
  );
}
