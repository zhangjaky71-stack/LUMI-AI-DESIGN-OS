"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "@/lib/api/problem";
import {
  compareVersions,
  forkVersionForUser,
  getSafeVersionProvenance,
  getVersionHistory,
  restoreVersionForUser,
} from "@/lib/versions/api";
import {
  semanticChanges,
  type SafeVersionProvenance,
  type SemanticChange,
  type VersionCompare,
  type VersionHistory,
  type VersionHistoryItem,
} from "@/lib/versions/types";
import type { ExactArtifactRef } from "@/lib/workspace/types";

export function VersionHistoryPanel({
  organizationId,
  artifact,
  onOpenVersion,
}: {
  organizationId: string;
  artifact: ExactArtifactRef;
  onOpenVersion: (value: ExactArtifactRef) => void;
}) {
  const [history, setHistory] = useState<VersionHistory | null>(null);
  const [provenance, setProvenance] = useState<SafeVersionProvenance | null>(null);
  const [compare, setCompare] = useState<VersionCompare | null>(null);
  const [compareBusy, setCompareBusy] = useState(false);
  const [expandedVersionId, setExpandedVersionId] = useState<string | null>(null);
  const [summaries, setSummaries] = useState<Record<string, readonly SemanticChange[]>>({});
  const [summaryBusyId, setSummaryBusyId] = useState<string | null>(null);
  const [forkName, setForkName] = useState("");
  const [restoreBranchId, setRestoreBranchId] = useState<string>("");
  const [pendingAction, setPendingAction] = useState<"fork" | "restore" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [newHeadId, setNewHeadId] = useState<string | null>(null);
  const initialHeadByBranch = useRef<Map<string, string | null> | null>(null);
  const mounted = useRef(true);

  const refresh = useCallback(async (background = false) => {
    try {
      const next = await getVersionHistory(organizationId, artifact.artifactId);
      if (!mounted.current) return;
      const heads = new Map(next.branches.map((branch) => [branch.id, branch.headVersionId]));
      if (initialHeadByBranch.current === null) {
        initialHeadByBranch.current = heads;
      } else if (background) {
        const viewed = next.versions.find((item) => item.id === artifact.artifactVersionId);
        if (viewed) {
          const initialHead = initialHeadByBranch.current.get(viewed.branchId) ?? null;
          const latestHead = heads.get(viewed.branchId) ?? null;
          if (latestHead && latestHead !== initialHead && latestHead !== artifact.artifactVersionId) {
            setNewHeadId(latestHead);
          }
        }
      }
      setHistory(next);
      setNotice(null);
    } catch (error) {
      if (!background && mounted.current) setNotice(message(error, "Version history is unavailable."));
    }
  }, [organizationId, artifact.artifactId, artifact.artifactVersionId]);

  useEffect(() => {
    mounted.current = true;
    initialHeadByBranch.current = null;
    setHistory(null);
    setCompare(null);
    setSummaries({});
    setExpandedVersionId(null);
    setNewHeadId(null);
    setRestoreBranchId("");
    void refresh(false);
    const poll = window.setInterval(() => void refresh(true), 10_000);
    return () => {
      mounted.current = false;
      window.clearInterval(poll);
    };
  }, [artifact.artifactId, refresh]);

  useEffect(() => {
    setProvenance(null);
    void getSafeVersionProvenance(organizationId, artifact.artifactVersionId)
      .then((value) => mounted.current && setProvenance(value))
      .catch((error) => mounted.current && setNotice(message(error, "Provenance is unavailable for this version.")));
  }, [organizationId, artifact.artifactVersionId]);

  const versions = useMemo(
    () => [...(history?.versions ?? [])].sort((left, right) => right.versionNumber - left.versionNumber),
    [history],
  );
  const branchesById = useMemo(
    () => new Map((history?.branches ?? []).map((branch) => [branch.id, branch])),
    [history],
  );
  const viewed = useMemo(
    () => versions.find((item) => item.id === artifact.artifactVersionId) ?? null,
    [versions, artifact.artifactVersionId],
  );

  useEffect(() => {
    if (!restoreBranchId && viewed) setRestoreBranchId(viewed.branchId);
  }, [restoreBranchId, viewed]);

  async function loadSummary(version: VersionHistoryItem) {
    setExpandedVersionId((current) => current === version.id ? null : version.id);
    if (!version.parentVersionId || summaries[version.id] || summaryBusyId) return;
    setSummaryBusyId(version.id);
    try {
      const result = await compareVersions(organizationId, version.parentVersionId, version.id);
      setSummaries((current) => ({ ...current, [version.id]: semanticChanges(result.semanticDiff) }));
    } catch (error) {
      setNotice(message(error, "Could not calculate this version summary."));
    } finally {
      setSummaryBusyId(null);
    }
  }

  async function compareWithViewed(candidate: VersionHistoryItem) {
    if (candidate.id === artifact.artifactVersionId || compareBusy) return;
    setCompareBusy(true);
    setNotice(null);
    try {
      const result = await compareVersions(organizationId, candidate.id, artifact.artifactVersionId);
      setCompare(result);
    } catch (error) {
      setNotice(message(error, "Could not compare the selected versions."));
    } finally {
      setCompareBusy(false);
    }
  }

  async function forkViewed() {
    const name = forkName.trim();
    if (!viewed || !name || pendingAction) return;
    setPendingAction("fork");
    setNotice(null);
    try {
      const branch = await forkVersionForUser(organizationId, viewed.id, name);
      setForkName("");
      await refresh(false);
      setRestoreBranchId(branch.id);
      setNotice(`Created branch “${branch.name}” from v${viewed.versionNumber}. No historical version was changed.`);
    } catch (error) {
      setNotice(message(error, "Could not fork this version."));
    } finally {
      setPendingAction(null);
    }
  }

  async function restoreViewed() {
    if (!viewed || !restoreBranchId || !history || pendingAction) return;
    const target = history.branches.find((branch) => branch.id === restoreBranchId);
    if (!target) return;
    setPendingAction("restore");
    setNotice(null);
    try {
      const restored = await restoreVersionForUser(
        organizationId,
        viewed.id,
        target.id,
        target.headVersionId,
      );
      await refresh(false);
      onOpenVersion({
        artifactId: artifact.artifactId,
        artifactVersionId: restored.id,
        versionNumber: restored.versionNumber,
        label: history.artifact.name,
      });
      setNotice(`Restored v${viewed.versionNumber} as new v${restored.versionNumber} on ${target.name}. Later history was preserved.`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        await refresh(false);
        setNotice("The branch head changed before restore. History was refreshed; review the latest head and retry.");
      } else {
        setNotice(message(error, "Could not restore this version."));
      }
    } finally {
      setPendingAction(null);
    }
  }

  function openVersion(version: VersionHistoryItem) {
    onOpenVersion({
      artifactId: artifact.artifactId,
      artifactVersionId: version.id,
      versionNumber: version.versionNumber,
      label: history?.artifact.name ?? artifact.label,
    });
  }

  return (
    <section className="version-panel" aria-labelledby="version-panel-title">
      <div className="version-panel-heading">
        <div>
          <p className="eyebrow">Versions</p>
          <h2 id="version-panel-title">History</h2>
        </div>
        <button type="button" className="version-text-button" onClick={() => void refresh(false)}>Refresh</button>
      </div>

      {newHeadId ? (
        <div className="version-update-banner" role="status">
          A newer branch head is available. Your current version and compare target were not changed.
          <button type="button" onClick={() => {
            const latest = versions.find((item) => item.id === newHeadId);
            if (latest) openVersion(latest);
          }}>Open new head</button>
        </div>
      ) : null}
      {notice ? <div className="version-notice" role="status">{notice}</div> : null}

      {!history ? <p className="version-muted">Loading immutable history…</p> : null}
      {history && versions.length === 0 ? <p className="version-muted">No versions recorded.</p> : null}

      <div className="version-list">
        {versions.map((version) => {
          const branch = branchesById.get(version.branchId);
          const isViewed = version.id === artifact.artifactVersionId;
          const isHead = branch?.headVersionId === version.id;
          const expanded = expandedVersionId === version.id;
          const summary = summaries[version.id];
          return (
            <article key={version.id} className={`version-card${isViewed ? " is-viewed" : ""}`}>
              <div className="version-card-top">
                <button type="button" className="version-open-button" onClick={() => openVersion(version)} aria-current={isViewed ? "true" : undefined}>
                  <span className="version-number">v{version.versionNumber}</span>
                  <span>{branch?.name ?? "unknown branch"}</span>
                </button>
                <div className="version-badges">
                  {isHead ? <span>HEAD</span> : null}
                  <span className={`status-${version.status.toLowerCase()}`}>{version.status}</span>
                </div>
              </div>
              <div className="version-meta">
                <span>{creatorLabel(version)}</span>
                <span>{formatTime(version.createdAt)}</span>
                {version.qualityScore !== null ? <span>Quality {Math.round(version.qualityScore * 100)}</span> : null}
              </div>
              <div className="version-card-actions">
                <button type="button" onClick={() => void loadSummary(version)}>{expanded ? "Hide changes" : "Changes"}</button>
                {!isViewed ? <button type="button" disabled={compareBusy} onClick={() => void compareWithViewed(version)}>Compare</button> : <span>Viewing</span>}
              </div>
              {expanded ? (
                <div className="version-summary">
                  {!version.parentVersionId ? <p>Initial version.</p> : summaryBusyId === version.id ? <p>Calculating structured diff…</p> : summary ? <ChangeList changes={summary} /> : <p>No structured semantic summary is available for this artifact type.</p>}
                </div>
              ) : null}
            </article>
          );
        })}
      </div>

      {compare ? <ComparePanel value={compare} versions={versions} onOpen={openVersion} onClose={() => setCompare(null)} /> : null}

      {viewed ? (
        <div className="version-actions-block">
          <p className="eyebrow">Branch from v{viewed.versionNumber}</p>
          <div className="version-inline-form">
            <input value={forkName} onChange={(event) => setForkName(event.target.value)} maxLength={120} placeholder="dark-direction" aria-label="New branch name" />
            <button type="button" disabled={!forkName.trim() || pendingAction !== null} onClick={() => void forkViewed()}>{pendingAction === "fork" ? "Forking…" : "Fork"}</button>
          </div>
        </div>
      ) : null}

      {viewed && history?.branches.length ? (
        <div className="version-actions-block version-restore-block">
          <p className="eyebrow">Restore</p>
          <p>Restore creates a new version on the selected branch. It never deletes later history.</p>
          <div className="version-inline-form">
            <select value={restoreBranchId} onChange={(event) => setRestoreBranchId(event.target.value)} aria-label="Restore target branch">
              {history.branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}
            </select>
            <button type="button" disabled={!restoreBranchId || pendingAction !== null} onClick={() => void restoreViewed()}>{pendingAction === "restore" ? "Restoring…" : "Restore as new"}</button>
          </div>
        </div>
      ) : null}

      <ProvenancePanel value={provenance} />
    </section>
  );
}

function ChangeList({ changes }: { changes: readonly SemanticChange[] }) {
  if (changes.length === 0) return <p>No semantic changes detected.</p>;
  return (
    <ul>
      {changes.slice(0, 40).map((change, index) => (
        <li key={`${change.category}-${change.subject}-${change.property ?? ""}-${index}`}>
          <strong>{change.category}</strong> · <code>{shortId(change.subject)}</code>{change.property ? <> · {change.property}</> : null}
        </li>
      ))}
      {changes.length > 40 ? <li>{changes.length - 40} more structured changes not expanded.</li> : null}
    </ul>
  );
}

function ComparePanel({ value, versions, onOpen, onClose }: {
  value: VersionCompare;
  versions: readonly VersionHistoryItem[];
  onOpen: (value: VersionHistoryItem) => void;
  onClose: () => void;
}) {
  const left = versions.find((item) => item.id === value.leftVersionId);
  const right = versions.find((item) => item.id === value.rightVersionId);
  const changes = semanticChanges(value.semanticDiff);
  return (
    <div className="version-compare-panel">
      <div className="version-panel-heading">
        <div><p className="eyebrow">Exact compare</p><h3>{left ? `v${left.versionNumber}` : shortId(value.leftVersionId)} → {right ? `v${right.versionNumber}` : shortId(value.rightVersionId)}</h3></div>
        <button type="button" className="version-text-button" onClick={onClose}>Close</button>
      </div>
      <p>{value.equalContentHash ? "Content hashes are identical." : `Comparison kind: ${value.kind.replaceAll("_", " ").toLowerCase()}.`}</p>
      {value.kind === "DESIGN_SEMANTIC" ? <ChangeList changes={changes} /> : null}
      {value.visualMetrics ? <dl className="version-metrics">{Object.entries(value.visualMetrics).map(([key, metric]) => <div key={key}><dt>{key}</dt><dd>{metric.toFixed(4)}</dd></div>)}</dl> : null}
      <div className="version-compare-actions">
        {left ? <button type="button" onClick={() => onOpen(left)}>Open left exact</button> : null}
        {right ? <button type="button" onClick={() => onOpen(right)}>Open right exact</button> : null}
      </div>
      <p className="version-muted">Visual overlay/wipe is not simulated when no canonical preview renderer is available.</p>
    </div>
  );
}

function ProvenancePanel({ value }: { value: SafeVersionProvenance | null }) {
  return (
    <div className="version-provenance">
      <p className="eyebrow">Provenance</p>
      {!value ? <p className="version-muted">Loading safe provenance…</p> : (
        <dl>
          <Info label="Traceability" value={`${Math.round(value.traceabilityScore * 100)}% · ${value.traceabilityStatus}`} />
          <Info label="Provider / model" value={[value.provider, value.model].filter(Boolean).join(" / ") || "—"} />
          <Info label="Agent / recipe" value={[value.agentVersion, value.recipeVersion].filter(Boolean).join(" / ") || "—"} />
          <Info label="Prompt hash" value={value.promptHash ? shortHash(value.promptHash) : "—"} />
          <Info label="Prompt template" value={value.promptTemplateVersion ?? "—"} />
          <Info label="Source assets" value={String(value.inputAssetIds.length)} />
          <Info label="Source versions" value={String(value.inputArtifactVersionIds.length)} />
          <Info label="Constraint snapshot" value={value.constraintSnapshotHash ? shortHash(value.constraintSnapshotHash) : "—"} />
          <Info label="Code" value={value.codeGitSha.slice(0, 10)} />
          <Info label="Compiler" value={value.compilerVersion ?? "—"} />
        </dl>
      )}
      <p className="version-muted">Raw prompts, system prompts, provider request IDs and private tool payloads are not exposed by this view.</p>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function creatorLabel(value: VersionHistoryItem): string { return value.createdById ? `${value.createdByType.toLowerCase()} · ${shortId(value.createdById)}` : value.createdByType.toLowerCase(); }
function formatTime(value: string): string { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date); }
function shortId(value: string): string { return value.length > 14 ? `${value.slice(0, 7)}…${value.slice(-4)}` : value; }
function shortHash(value: string): string { return `${value.slice(0, 10)}…${value.slice(-6)}`; }
function message(error: unknown, fallback: string): string { if (error instanceof ApiError) return error.detail || error.title || fallback; return error instanceof Error ? error.message : fallback; }
