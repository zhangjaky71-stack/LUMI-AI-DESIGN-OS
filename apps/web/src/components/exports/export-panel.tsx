"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { ApiError } from "@/lib/api/problem";
import {
  cancelExportJob,
  createExportJob,
  createExportTask,
  getExportCapabilities,
  getExportJob,
  issueExportDownload,
} from "@/lib/exports/api";
import type { ExportCapabilities, ExportFormat, ExportJob } from "@/lib/exports/types";
import type { ExactArtifactRef } from "@/lib/workspace/types";

type CandidateState = {
  artifact: ExactArtifactRef;
  capability: ExportCapabilities | null;
  error: string | null;
};

type SelectionState = {
  checked: boolean;
  format: ExportFormat | null;
  outputName: string;
};

const ACTIVE = new Set<ExportJob["status"]>(["PLANNED", "QUEUED", "RENDERING", "PACKAGING"]);
const STAGES = ["PLANNED", "QUEUED", "RENDERING", "PACKAGING", "READY"] as const;

export function ExportPanel({
  organizationId,
  projectId,
  currentArtifact,
  availableArtifacts,
}: {
  organizationId: string;
  projectId: string;
  currentArtifact: ExactArtifactRef;
  availableArtifacts: readonly ExactArtifactRef[];
}) {
  const candidates = useMemo(() => dedupeArtifacts([currentArtifact, ...availableArtifacts]), [currentArtifact, availableArtifacts]);
  const [capabilities, setCapabilities] = useState<Record<string, CandidateState>>({});
  const [selection, setSelection] = useState<Record<string, SelectionState>>({});
  const [job, setJob] = useState<ExportJob | null>(null);
  const [pending, setPending] = useState<"create" | "cancel" | "download" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastDownloadExpiry, setLastDownloadExpiry] = useState<string | null>(null);
  const loadEpoch = useRef(0);

  useEffect(() => {
    const epoch = ++loadEpoch.current;
    setCapabilities({});
    setSelection({});
    setJob(null);
    setNotice(null);
    setLastDownloadExpiry(null);
    void Promise.all(
      candidates.map(async (artifact) => {
        try {
          const capability = await getExportCapabilities(organizationId, projectId, artifact.artifactVersionId);
          return { artifact, capability, error: null } satisfies CandidateState;
        } catch (error) {
          return { artifact, capability: null, error: message(error, "This exact version is not exportable.") } satisfies CandidateState;
        }
      }),
    ).then((values) => {
      if (epoch !== loadEpoch.current) return;
      const nextCapabilities: Record<string, CandidateState> = {};
      const nextSelection: Record<string, SelectionState> = {};
      for (const value of values) {
        nextCapabilities[value.artifact.artifactVersionId] = value;
        const first = value.capability?.formats[0] ?? null;
        nextSelection[value.artifact.artifactVersionId] = {
          checked: value.artifact.artifactVersionId === currentArtifact.artifactVersionId && first !== null,
          format: first?.format ?? null,
          outputName: first ? defaultOutputName(value.artifact, first.outputExtension) : "",
        };
      }
      setCapabilities(nextCapabilities);
      setSelection(nextSelection);
    });
  }, [organizationId, projectId, currentArtifact.artifactVersionId, candidates]);

  useEffect(() => {
    if (!job || !ACTIVE.has(job.status)) return;
    let cancelled = false;
    const timer = window.setInterval(() => {
      void getExportJob(organizationId, job.jobId)
        .then((fresh) => {
          if (!cancelled) setJob(fresh);
        })
        .catch((error) => {
          if (!cancelled) setNotice(message(error, "Could not refresh export progress."));
        });
    }, 2_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [organizationId, job?.jobId, job?.status]);

  const selectedItems = useMemo(() => {
    const items: { artifact: ExactArtifactRef; targetFormat: ExportFormat; outputName: string }[] = [];
    for (const artifact of candidates) {
      const state = selection[artifact.artifactVersionId];
      if (!state?.checked || !state.format || !state.outputName.trim()) continue;
      items.push({ artifact, targetFormat: state.format, outputName: state.outputName.trim() });
    }
    return items;
  }, [candidates, selection]);

  async function createExport() {
    if (!selectedItems.length || pending || (job && ACTIVE.has(job.status))) return;
    setPending("create");
    setNotice(null);
    setLastDownloadExpiry(null);
    try {
      const taskId = await createExportTask(
        organizationId,
        projectId,
        selectedItems.map((item) => item.artifact.artifactVersionId),
      );
      const created = await createExportJob(
        organizationId,
        projectId,
        taskId,
        selectedItems.map((item) => ({
          artifactVersionId: item.artifact.artifactVersionId,
          targetFormat: item.targetFormat,
          outputName: item.outputName,
        })),
      );
      setJob(created);
      setNotice(created.status === "READY" ? "Export is ready." : "Export job created from the selected exact versions.");
    } catch (error) {
      setNotice(message(error, "Could not create export job."));
    } finally {
      setPending(null);
    }
  }

  async function cancelJob() {
    if (!job || !ACTIVE.has(job.status) || pending) return;
    setPending("cancel");
    try {
      setJob(await cancelExportJob(organizationId, job.jobId));
      setNotice("Export cancellation requested. Completed immutable outputs are not rewritten.");
    } catch (error) {
      setNotice(message(error, "Could not cancel export."));
    } finally {
      setPending(null);
    }
  }

  async function download() {
    if (!job || job.status !== "READY" || pending) return;
    setPending("download");
    setNotice(null);
    try {
      const grant = await issueExportDownload(organizationId, job.jobId);
      setLastDownloadExpiry(grant.expiresAt);
      openSignedUrl(grant.url);
      setNotice(`Signed download issued for ${grant.filename}. Request Download again after expiry; the READY package is reused.`);
    } catch (error) {
      setNotice(message(error, "Could not issue a signed download."));
    } finally {
      setPending(null);
    }
  }

  return (
    <section className="export-panel" aria-labelledby="export-panel-title">
      <div className="export-panel-heading">
        <div><p className="eyebrow">Export</p><h2 id="export-panel-title">Exact versions</h2></div>
        {job ? <span className={`export-status export-status-${job.status.toLowerCase()}`}>{job.status}</span> : null}
      </div>
      <p className="export-copy">Only renderer-verified formats are shown for each exact APPROVED ArtifactVersion. Export never resolves “latest”.</p>

      <div className="export-capability-note">
        <strong>Current runtime:</strong> verified copy-through only. No AI generation fee. Resize, quality, alpha, print/CMYK, crop and AI Adapt are unavailable until the renderer exposes them.
      </div>

      <div className="export-candidate-list">
        {candidates.map((artifact) => {
          const state = capabilities[artifact.artifactVersionId];
          const chosen = selection[artifact.artifactVersionId];
          const current = artifact.artifactVersionId === currentArtifact.artifactVersionId;
          return (
            <article key={artifact.artifactVersionId} className={`export-candidate${current ? " is-current" : ""}`}>
              <div className="export-candidate-title">
                <label>
                  <input
                    type="checkbox"
                    checked={chosen?.checked ?? false}
                    disabled={!state?.capability || pending !== null || Boolean(job && ACTIVE.has(job.status))}
                    onChange={(event) => patchSelection(setSelection, artifact.artifactVersionId, { checked: event.target.checked })}
                  />
                  <span>{artifact.label ?? "Artifact"} {artifact.versionNumber ? `· v${artifact.versionNumber}` : ""}</span>
                </label>
                {current ? <span>VIEWING</span> : null}
              </div>
              {!state ? <p className="export-muted">Checking exact-version capability…</p> : state.error ? <p className="export-error">{state.error}</p> : state.capability ? (
                <div className="export-candidate-controls">
                  <select
                    aria-label={`Format for ${artifact.label ?? artifact.artifactVersionId}`}
                    value={chosen?.format ?? ""}
                    disabled={!chosen?.checked || pending !== null || Boolean(job && ACTIVE.has(job.status))}
                    onChange={(event) => {
                      const format = event.target.value as ExportFormat;
                      const capability = state.capability?.formats.find((item) => item.format === format);
                      patchSelection(setSelection, artifact.artifactVersionId, {
                        format,
                        ...(capability ? { outputName: defaultOutputName(artifact, capability.outputExtension) } : {}),
                      });
                    }}
                  >
                    {state.capability.formats.map((format) => <option key={format.format} value={format.format}>{format.label}</option>)}
                  </select>
                  <input
                    aria-label={`Output filename for ${artifact.label ?? artifact.artifactVersionId}`}
                    value={chosen?.outputName ?? ""}
                    disabled={!chosen?.checked || pending !== null || Boolean(job && ACTIVE.has(job.status))}
                    onChange={(event) => patchSelection(setSelection, artifact.artifactVersionId, { outputName: event.target.value })}
                    maxLength={240}
                  />
                  <small>{state.capability.sourceMimeType}</small>
                </div>
              ) : null}
            </article>
          );
        })}
      </div>

      <div className="export-summary-row">
        <span>{selectedItems.length} exact version{selectedItems.length === 1 ? "" : "s"}</span>
        <span>{selectedItems.length > 1 ? "ZIP package" : "single output"}</span>
        <button type="button" disabled={!selectedItems.length || pending !== null || Boolean(job && ACTIVE.has(job.status))} onClick={() => void createExport()}>{pending === "create" ? "Creating…" : "Create export"}</button>
      </div>

      {job ? <ExportJobView job={job} lastDownloadExpiry={lastDownloadExpiry} onCancel={cancelJob} onDownload={download} pending={pending} /> : null}
      {notice ? <div className="export-notice" role="status">{notice}</div> : null}
    </section>
  );
}

function ExportJobView({
  job,
  lastDownloadExpiry,
  onCancel,
  onDownload,
  pending,
}: {
  job: ExportJob;
  lastDownloadExpiry: string | null;
  onCancel: () => Promise<void>;
  onDownload: () => Promise<void>;
  pending: "create" | "cancel" | "download" | null;
}) {
  const stage = STAGES.indexOf(job.status as (typeof STAGES)[number]);
  return (
    <div className="export-job">
      <div className="export-stage-list" aria-label="Export progress">
        {STAGES.map((item, index) => <span key={item} className={stage >= index ? "is-complete" : ""}>{item}</span>)}
      </div>
      {job.errorCode ? <p className="export-error">{job.errorCode}</p> : null}
      <div className="export-job-actions">
        {ACTIVE.has(job.status) ? <button type="button" disabled={pending !== null} onClick={() => void onCancel()}>{pending === "cancel" ? "Cancelling…" : "Cancel"}</button> : null}
        {job.status === "READY" ? <button type="button" disabled={pending !== null} onClick={() => void onDownload()}>{pending === "download" ? "Signing…" : "Download"}</button> : null}
      </div>
      {lastDownloadExpiry ? <p className="export-muted">Last signed URL expires {formatTime(lastDownloadExpiry)}. Signing again does not rerender.</p> : null}
      {job.package ? (
        <dl className="export-package-meta">
          <Info label="Package" value={job.package.filename} />
          <Info label="Size" value={formatBytes(job.package.sizeBytes)} />
          <Info label="SHA-256" value={shortHash(job.package.checksumSha256)} />
          <Info label="Archive" value={job.package.isArchive ? "ZIP" : "No"} />
        </dl>
      ) : null}
      {job.manifest ? (
        <details className="export-manifest">
          <summary>Manifest · {job.manifest.entries.length} file{job.manifest.entries.length === 1 ? "" : "s"}</summary>
          <p>Operation {shortId(job.manifest.operationId)} · exporter {job.manifest.exporterVersion}</p>
          <ul>{job.manifest.entries.map((entry) => <li key={`${entry.artifactVersionId}-${entry.name}`}><span>{entry.name}</span><small>v {shortId(entry.artifactVersionId)} · {formatBytes(entry.sizeBytes)} · {shortHash(entry.checksumSha256)}</small></li>)}</ul>
        </details>
      ) : null}
      {job.status === "FAILED" ? <p className="export-muted">Partial per-item retry is not exposed because the current NODE-49 job model fails the job as a whole.</p> : null}
      {job.status === "EXPIRED" ? <p className="export-muted">This export job is expired and cannot issue a new download grant.</p> : null}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function patchSelection(setter: Dispatch<SetStateAction<Record<string, SelectionState>>>, id: string, patch: Partial<SelectionState>) { setter((current) => ({ ...current, [id]: { ...(current[id] ?? { checked: false, format: null, outputName: "" }), ...patch } })); }
function dedupeArtifacts(values: readonly ExactArtifactRef[]): ExactArtifactRef[] { const seen = new Set<string>(); return values.filter((item) => { if (seen.has(item.artifactVersionId)) return false; seen.add(item.artifactVersionId); return true; }); }
function defaultOutputName(artifact: ExactArtifactRef, extension: string): string { const base = (artifact.label ?? "artifact").replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "artifact"; const version = artifact.versionNumber ? `-v${artifact.versionNumber}` : ""; return `${base}${version}.${extension}`.slice(0, 240); }
function openSignedUrl(value: string) { const url = new URL(value, window.location.origin); const localHttp = url.protocol === "http:" && ["localhost", "127.0.0.1", "::1"].includes(url.hostname); if (url.protocol !== "https:" && !localHttp) throw new Error("EXPORT_DOWNLOAD_URL_PROTOCOL_FORBIDDEN"); window.location.assign(url.toString()); }
function formatBytes(value: number): string { if (value < 1024) return `${value} B`; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; return `${(value / (1024 * 1024)).toFixed(1)} MB`; }
function formatTime(value: string): string { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date); }
function shortHash(value: string): string { return `${value.slice(0, 10)}…${value.slice(-6)}`; }
function shortId(value: string): string { return value.length > 14 ? `${value.slice(0, 7)}…${value.slice(-4)}` : value; }
function message(error: unknown, fallback: string): string { if (error instanceof ApiError) return error.detail || error.title || fallback; return error instanceof Error ? error.message : fallback; }
