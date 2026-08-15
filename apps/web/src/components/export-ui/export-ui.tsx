"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ExportFormat, ExportResizeMode } from "@lumi/artifact-sdk";
import {
  buildExportSpec,
  capabilitiesForSource,
  estimateExport,
  hasAspectRatioChange,
  safeExportError,
  safeFilename,
  statusLabel,
} from "@/lib/export-ui/contracts";
import { createExportGateway } from "@/lib/export-ui/export-gateway";
import type {
  ExportBootstrap,
  ExportDownloadLease,
  ExportHistoryItem,
  ExportJobView,
  ExportSourceOption,
  ExportWorkspaceSnapshot,
} from "@/lib/export-ui/types";
import styles from "./export-ui.module.css";

const PRESETS = [
  { id: "instagram-square", label: "Instagram 1:1", width: 1080, height: 1080 },
  { id: "instagram-story", label: "Story 9:16", width: 1080, height: 1920 },
  { id: "social-landscape", label: "Social 16:9", width: 1920, height: 1080 },
] as const;

function bytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function exactLabel(source: ExportSourceOption): string {
  return `${source.artifact_version_id} · ${source.design_document_version_id}`;
}

export function ExportUI({ projectId, bootstrap }: { projectId: string; bootstrap: ExportBootstrap }) {
  const gatewayRef = useRef(createExportGateway(bootstrap));
  const [workspace, setWorkspace] = useState<ExportWorkspaceSnapshot | null>(bootstrap.workspace);
  const [sourceId, setSourceId] = useState(bootstrap.workspace?.active_source_id ?? "");
  const [format, setFormat] = useState<ExportFormat>("PNG");
  const [sizeMode, setSizeMode] = useState<"ORIGINAL" | "2X" | "CUSTOM" | "PRESET">("ORIGINAL");
  const [width, setWidth] = useState(1080);
  const [height, setHeight] = useState(1350);
  const [resizeMode, setResizeMode] = useState<ExportResizeMode>("SCALE");
  const [quality, setQuality] = useState(90);
  const [alpha, setAlpha] = useState(false);
  const [includeManifest, setIncludeManifest] = useState(true);
  const [filename, setFilename] = useState("summer-launch");
  const [job, setJob] = useState<ExportJobView | null>(null);
  const [history, setHistory] = useState<readonly ExportHistoryItem[]>(bootstrap.workspace?.history ?? []);
  const [lease, setLease] = useState<ExportDownloadLease | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!bootstrap.workspace);

  useEffect(() => {
    if (bootstrap.workspace) return;
    const controller = new AbortController();
    setLoading(true);
    gatewayRef.current.loadWorkspace(projectId, controller.signal)
      .then((snapshot) => {
        setWorkspace(snapshot);
        setSourceId(snapshot.active_source_id ?? snapshot.sources[0]?.id ?? "");
        setHistory(snapshot.history);
      })
      .catch(() => setError("Export workspace could not be loaded."))
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [bootstrap.workspace, projectId]);

  const source = useMemo(
    () => workspace?.sources.find((item) => item.id === sourceId) ?? workspace?.sources[0] ?? null,
    [sourceId, workspace],
  );
  const capabilities = useMemo(
    () => source && workspace ? capabilitiesForSource(source, workspace.capabilities) : [],
    [source, workspace],
  );
  const selectedCapability = capabilities.find((item) => item.format === format) ?? capabilities[0] ?? null;

  useEffect(() => {
    if (!source) return;
    if (sizeMode === "ORIGINAL") { setWidth(source.width); setHeight(source.height); }
    if (sizeMode === "2X") { setWidth(source.width * 2); setHeight(source.height * 2); }
  }, [sizeMode, source]);

  useEffect(() => {
    if (!selectedCapability && capabilities[0]) setFormat(capabilities[0].format);
  }, [capabilities, selectedCapability]);

  useEffect(() => {
    if (!job || ["READY", "FAILED", "EXPIRED"].includes(job.status)) return;
    const timer = window.setTimeout(() => {
      gatewayRef.current.getExport(job.export_job_id)
        .then(async (next) => {
          setJob(next);
          if (["READY", "FAILED", "EXPIRED"].includes(next.status)) {
            setHistory(await gatewayRef.current.listHistory(projectId));
          }
        })
        .catch(() => setError("Export status refresh failed. The job was not recreated."));
    }, bootstrap.mode === "DETERMINISTIC" ? 180 : 1800);
    return () => window.clearTimeout(timer);
  }, [bootstrap.mode, job, projectId]);

  if (loading) return <main className={styles.shell}><div className={styles.loading}>Loading governed export workspace…</div></main>;
  if (!workspace || !source || !selectedCapability) return <main className={styles.shell}><div className={styles.empty}>No exact exportable version is available.</div></main>;

  const ratioChanged = hasAspectRatioChange(source, width, height);
  const estimate = estimateExport(source, selectedCapability.format);
  const terminal = job && ["READY", "FAILED", "EXPIRED"].includes(job.status);

  async function submitExport() {
    setError(null); setNotice(null); setLease(null);
    try {
      const spec = buildExportSpec({
        organizationId: workspace!.organization_id,
        projectId,
        actorId: workspace!.actor_id,
        operationId: crypto.randomUUID(),
        draft: {
          source: source!, format: selectedCapability!.format, size_mode: sizeMode,
          target_width: width, target_height: height, resize_mode: resizeMode,
          quality: selectedCapability!.supports_quality ? quality : null,
          transparent_background: selectedCapability!.supports_alpha ? alpha : false,
          include_manifest: includeManifest, filename: safeFilename(filename),
        },
      });
      const created = await gatewayRef.current.createExport(spec);
      setJob(created);
      setNotice(`Exact source frozen: ${created.artifact_version_id} / ${created.design_document_version_id}`);
    } catch (caught) {
      const code = caught instanceof Error ? caught.message : undefined;
      setError(safeExportError(code));
    }
  }

  async function refreshSignedDownload(fileId: string) {
    if (!job) return;
    setError(null);
    try {
      const next = await gatewayRef.current.getDownload(job.export_job_id, fileId);
      setLease(next);
      setNotice("A fresh short-lived signed download was issued. Export files were not rendered again.");
    } catch (caught) {
      setError(safeExportError(caught instanceof Error ? caught.message : undefined));
    }
  }

  return (
    <main className={styles.shell} data-testid="export-ui">
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>LUMI / DELIVERY</p>
          <h1>Export Center</h1>
          <p>Export an immutable design version through the verified NODE-49 pipeline.</p>
        </div>
        <div className={styles.headerActions}>
          <Link href={`/app/projects/${encodeURIComponent(projectId)}/versions`}>Version history</Link>
          <Link href={`/app/projects/${encodeURIComponent(projectId)}/workspace`}>Workspace</Link>
        </div>
      </header>

      {(notice || error) && <div className={error ? styles.error : styles.notice} role="status">{error ?? notice}</div>}

      <div className={styles.grid}>
        <section className={styles.panel}>
          <div className={styles.sectionTitle}><span>01</span><div><h2>Exact source</h2><p>No floating latest/head/current resolution.</p></div></div>
          <label className={styles.field}>Source
            <select value={source.id} onChange={(event) => { setSourceId(event.target.value); setJob(null); setLease(null); }} data-testid="source-select">
              {workspace.sources.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </label>
          <div className={styles.versionLock} data-testid="exact-version-lock">
            <div><span>ArtifactVersion</span><strong>{source.artifact_version_id}</strong></div>
            <div><span>DesignVersion</span><strong>{source.design_document_version_id}</strong></div>
            <div><span>BrandRuleSet</span><strong>{source.brand_rule_set_version ?? "Not bound"}</strong></div>
          </div>
          <p className={styles.micro}>{source.frame_ids.length} frame{source.frame_ids.length === 1 ? "" : "s"} · {source.width}×{source.height} · {source.approved ? "Approved source" : "Draft source"}</p>
        </section>

        <section className={styles.panel}>
          <div className={styles.sectionTitle}><span>02</span><div><h2>Format</h2><p>Only verified capabilities are shown.</p></div></div>
          <div className={styles.formatGrid} data-testid="format-options">
            {capabilities.map((item) => (
              <button key={item.format} className={format === item.format ? styles.formatActive : styles.formatButton} onClick={() => setFormat(item.format)}>{item.label}</button>
            ))}
          </div>
          <p className={styles.micro} data-testid="unsupported-hidden">CMYK · Display P3 · PSD · bleed · crop marks are hidden until verified.</p>
        </section>

        <section className={styles.panel}>
          <div className={styles.sectionTitle}><span>03</span><div><h2>Size & geometry</h2><p>Export only scales or crops. Adapt creates a new version first.</p></div></div>
          <div className={styles.segmented}>
            {(["ORIGINAL", "2X", "CUSTOM", "PRESET"] as const).map((mode) => <button key={mode} className={sizeMode === mode ? styles.segmentActive : ""} onClick={() => setSizeMode(mode)}>{mode === "2X" ? "2×" : mode[0] + mode.slice(1).toLowerCase()}</button>)}
          </div>
          {sizeMode === "PRESET" && <label className={styles.field}>Preset<select onChange={(event) => { const preset = PRESETS.find((item) => item.id === event.target.value) ?? PRESETS[0]; setWidth(preset.width); setHeight(preset.height); }} defaultValue={PRESETS[0].id}>{PRESETS.map((preset) => <option key={preset.id} value={preset.id}>{preset.label} · {preset.width}×{preset.height}</option>)}</select></label>}
          {(sizeMode === "CUSTOM" || sizeMode === "PRESET") && <div className={styles.dimensionRow}><label>W<input type="number" min={1} value={width} onChange={(event) => setWidth(Number(event.target.value))} /></label><span>×</span><label>H<input type="number" min={1} value={height} onChange={(event) => setHeight(Number(event.target.value))} /></label></div>}
          {ratioChanged && <div className={styles.adaptCard} data-testid="aspect-ratio-choice"><div><strong>Aspect ratio changes</strong><p>Choose Crop/Scale for deterministic export geometry, or adapt the design before exporting.</p></div><div className={styles.choiceRow}><button className={resizeMode === "CROP" ? styles.choiceActive : ""} onClick={() => setResizeMode("CROP")}>Crop</button><button className={resizeMode === "SCALE" ? styles.choiceActive : ""} onClick={() => setResizeMode("SCALE")}>Scale</button><Link data-testid="ai-adapt-link" href={`/app/projects/${encodeURIComponent(projectId)}/workspace?adaptFromDesignVersion=${encodeURIComponent(source.design_document_version_id)}&target=${width}x${height}`}>Adapt design with AI → new DesignVersion</Link></div></div>}
        </section>

        <section className={styles.panel}>
          <div className={styles.sectionTitle}><span>04</span><div><h2>Output</h2><p>Renderer-backed controls only.</p></div></div>
          {selectedCapability.supports_quality && <label className={styles.field}>Quality <span>{quality}</span><input type="range" min={1} max={100} value={quality} onChange={(event) => setQuality(Number(event.target.value))} /></label>}
          {selectedCapability.supports_alpha && <label className={styles.check}><input type="checkbox" checked={alpha} onChange={(event) => setAlpha(event.target.checked)} /> Transparent background</label>}
          <label className={styles.check}><input type="checkbox" checked={includeManifest} onChange={(event) => setIncludeManifest(event.target.checked)} /> Include provenance manifest</label>
          <label className={styles.field}>Filename<input value={filename} onChange={(event) => setFilename(event.target.value)} /></label>
          <div className={styles.estimate} data-testid="cost-estimate"><span>Estimate</span><strong>{estimate.ai_generation_cost === 0 ? "No AI generation charge" : `$${estimate.ai_generation_cost}`}</strong><p>{estimate.render_label}. {estimate.note}</p></div>
        </section>
      </div>

      <section className={`${styles.panel} ${styles.jobPanel}`}>
        <div className={styles.sectionTitle}><span>05</span><div><h2>Export job</h2><p>Service-reported lifecycle. No synthetic 99% progress.</p></div></div>
        {!job ? <button className={styles.primary} onClick={submitExport} data-testid="create-export">Create export</button> : <div className={styles.job}>
          <div className={styles.jobTop}><div><span className={styles.status}>{statusLabel(job.status)}</span><code>{job.export_job_id}</code></div><strong>{job.status === "READY" ? "Verified" : job.status === "FAILED" ? "Needs attention" : "In progress"}</strong></div>
          <div className={styles.progressTrack} aria-label={`Service reported progress ${job.progress}`}><span style={{ width: `${Math.max(0, Math.min(100, job.progress))}%` }} /></div>
          <div className={styles.exactRow}><span>Frozen source</span><code>{job.artifact_version_id}</code><code>{job.design_document_version_id}</code></div>
          {job.error_code && <div className={styles.failure}><strong>{safeExportError(job.error_code)}</strong><small>Code: {job.error_code}</small>{!workspace.partial_retry_supported && <p data-testid="partial-retry-boundary">NODE-49 V1 has job-level failure only. Per-frame retry is intentionally unavailable rather than simulated.</p>}</div>}
          {job.status === "READY" && <div className={styles.files}>{job.files.map((file) => <div className={styles.file} key={file.file_id}><div><strong>{file.filename}</strong><span>{bytes(file.size_bytes)} · SHA-256 {file.checksum_sha256.slice(0, 12)}…</span></div><button onClick={() => refreshSignedDownload(file.file_id)}>Get fresh download</button></div>)}</div>}
          {lease && <div className={styles.downloadLease} data-testid="signed-download"><div><strong>Signed download ready</strong><span>Expires {new Date(lease.expires_at).toLocaleString()}</span></div><a href={lease.url} target="_blank" rel="noreferrer">Download {lease.filename}</a></div>}
          {terminal && <button className={styles.secondary} onClick={() => { setJob(null); setLease(null); }}>New export from exact version</button>}
        </div>}
      </section>

      <section className={`${styles.panel} ${styles.historyPanel}`}>
        <div className={styles.sectionTitle}><span>06</span><div><h2>Export history</h2><p>Jobs remain traceable to exact immutable source versions.</p></div></div>
        <div className={styles.history} data-testid="export-history">{history.map((item) => <article key={item.export_job_id}><div><span className={styles.status}>{statusLabel(item.status)}</span><code>{item.export_job_id}</code></div><p>{item.artifact_version_id}<br />{item.design_document_version_id}</p><div className={styles.historyMeta}><span>{item.files.length} file(s)</span><span>{item.manifest_available ? "Manifest" : "No manifest"}</span></div>{item.error_code && <small>{safeExportError(item.error_code)}</small>}</article>)}</div>
      </section>

      <footer className={styles.footer}><span>{workspace.export_engine_version}</span><span>Exact source · SRGB · signed download · no persisted signed URL</span></footer>
    </main>
  );
}
