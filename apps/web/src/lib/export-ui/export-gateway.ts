import type { ExportFormat, ExportJobStatus, ExportSpec } from "@lumi/artifact-sdk";
import { LumiApiClient, LumiApiError } from "@/lib/app-shell/api-client";
import { exportProblem } from "./contracts";
import type {
  ExportBootstrap,
  ExportDownloadLease,
  ExportHistoryItem,
  ExportJobView,
  ExportWorkspaceSnapshot,
} from "./types";

export interface ExportGateway {
  loadWorkspace(projectId: string, signal?: AbortSignal): Promise<ExportWorkspaceSnapshot>;
  createExport(spec: ExportSpec, signal?: AbortSignal): Promise<ExportJobView>;
  getExport(exportJobId: string, signal?: AbortSignal): Promise<ExportJobView>;
  getDownload(exportJobId: string, fileId: string, signal?: AbortSignal): Promise<ExportDownloadLease>;
  listHistory(projectId: string, signal?: AbortSignal): Promise<readonly ExportHistoryItem[]>;
}

function request(signal?: AbortSignal): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

function mapApiError(error: unknown): never {
  if (error instanceof LumiApiError) {
    const requestId = error.problem.request_id ?? null;
    const safe = exportProblem(error.problem.code, error.problem.status, requestId);
    safe.message = requestId ? `${error.problem.code}::request:${requestId}` : error.problem.code;
    throw safe;
  }
  throw error;
}

export class HttpExportGateway implements ExportGateway {
  readonly #api: LumiApiClient;
  constructor(api = new LumiApiClient()) { this.#api = api; }

  loadWorkspace(projectId: string, signal?: AbortSignal) {
    return this.#api
      .get<ExportWorkspaceSnapshot>(`/projects/${encodeURIComponent(projectId)}/exports`, request(signal))
      .catch(mapApiError);
  }

  createExport(spec: ExportSpec, signal?: AbortSignal) {
    return this.#api
      .post<ExportJobView, ExportSpec>("/exports", spec, {
        idempotency_key: spec.operation_id,
        ...request(signal),
      })
      .catch(mapApiError);
  }

  getExport(exportJobId: string, signal?: AbortSignal) {
    return this.#api
      .get<ExportJobView>(`/exports/${encodeURIComponent(exportJobId)}`, request(signal))
      .catch(mapApiError);
  }

  getDownload(exportJobId: string, fileId: string, signal?: AbortSignal) {
    return this.#api
      .post<ExportDownloadLease, { expires_seconds: number }>(
        `/exports/${encodeURIComponent(exportJobId)}/files/${encodeURIComponent(fileId)}:download`,
        { expires_seconds: 300 },
        request(signal),
      )
      .catch(mapApiError);
  }

  async listHistory(projectId: string, signal?: AbortSignal) {
    try {
      const response = await this.#api.get<{ items: readonly ExportHistoryItem[] }>(
        `/projects/${encodeURIComponent(projectId)}/exports/history`,
        request(signal),
      );
      return response.items;
    } catch (error) {
      return mapApiError(error);
    }
  }
}

function clone<T>(value: T): T { return structuredClone(value); }

export class DeterministicExportGateway implements ExportGateway {
  readonly #workspace: ExportWorkspaceSnapshot;
  readonly #jobs = new Map<string, ExportJobView>();
  readonly #specs = new Map<string, ExportSpec>();
  #counter = 60;
  #downloadCounter = 0;

  constructor(workspace: ExportWorkspaceSnapshot) {
    this.#workspace = clone(workspace);
    for (const item of workspace.history) {
      this.#jobs.set(item.export_job_id, {
        export_job_id: item.export_job_id,
        status: item.status,
        progress: item.status === "READY" ? 100 : 0,
        artifact_version_id: item.artifact_version_id,
        design_document_version_id: item.design_document_version_id,
        export_fingerprint: `fixture-${item.export_job_id}`,
        files: clone(item.files),
        ...(item.error_code ? { error_code: item.error_code } : {}),
      });
    }
  }

  async loadWorkspace(projectId: string, signal?: AbortSignal) {
    this.#assert(signal);
    if (projectId !== this.#workspace.project_id) throw exportProblem("EXPORT_PROJECT_NOT_FOUND", 404);
    return clone({ ...this.#workspace, history: await this.listHistory(projectId, signal) });
  }

  async createExport(spec: ExportSpec, signal?: AbortSignal) {
    this.#assert(signal);
    if (/^(latest|head|current)$/i.test(spec.artifact_version_id) || /^(latest|head|current)$/i.test(spec.design_document_version_id)) {
      throw exportProblem("EXPORT_VERSION_MUST_BE_EXACT");
    }
    const existing = [...this.#specs.entries()].find(([, value]) => value.operation_id === spec.operation_id);
    if (existing) return clone(this.#jobs.get(existing[0])!);
    const id = `export-job-${++this.#counter}`;
    const job: ExportJobView = {
      export_job_id: id,
      status: "PENDING",
      progress: 0,
      artifact_version_id: spec.artifact_version_id,
      design_document_version_id: spec.design_document_version_id,
      export_fingerprint: `sha256:export-${this.#counter}`,
      files: [],
    };
    this.#specs.set(id, clone(spec));
    this.#jobs.set(id, job);
    return clone(job);
  }

  async getExport(exportJobId: string, signal?: AbortSignal) {
    this.#assert(signal);
    const current = this.#jobs.get(exportJobId);
    if (!current) throw exportProblem("EXPORT_JOB_NOT_FOUND", 404);
    if (current.status === "READY" || current.status === "FAILED" || current.status === "EXPIRED") return clone(current);
    const next = this.#advance(current);
    this.#jobs.set(exportJobId, next);
    return clone(next);
  }

  async getDownload(exportJobId: string, fileId: string, signal?: AbortSignal) {
    this.#assert(signal);
    const job = this.#jobs.get(exportJobId);
    if (!job || job.status !== "READY") throw exportProblem("EXPORT_DOWNLOAD_NOT_READY", 409);
    const file = job.files.find((item) => item.file_id === fileId);
    if (!file) throw exportProblem("EXPORT_FILE_NOT_FOUND", 404);
    this.#downloadCounter += 1;
    return {
      url: `https://signed.invalid/${encodeURIComponent(file.filename)}?lease=${this.#downloadCounter}&ttl=300`,
      expires_at: new Date(Date.parse("2030-01-01T00:00:00.000Z") + this.#downloadCounter * 300_000).toISOString(),
      filename: file.filename,
    };
  }

  async listHistory(projectId: string, signal?: AbortSignal) {
    this.#assert(signal);
    if (projectId !== this.#workspace.project_id) throw exportProblem("EXPORT_PROJECT_NOT_FOUND", 404);
    const generated: ExportHistoryItem[] = [];
    for (const job of this.#jobs.values()) {
      if (!job.export_job_id.startsWith("export-job-")) continue;
      generated.push({
        export_job_id: job.export_job_id,
        artifact_version_id: job.artifact_version_id,
        design_document_version_id: job.design_document_version_id,
        status: job.status,
        created_at: "2026-08-15T05:58:00.000Z",
        files: clone(job.files),
        manifest_available: job.status === "READY",
        ...(job.error_code ? { error_code: job.error_code } : {}),
      });
    }
    return clone([...generated.reverse(), ...this.#workspace.history]);
  }

  #advance(job: ExportJobView): ExportJobView {
    const next: Record<ExportJobStatus, { status: ExportJobStatus; progress: number }> = {
      PENDING: { status: "RENDERING", progress: 25 },
      RENDERING: { status: "PACKAGING", progress: 60 },
      PACKAGING: { status: "VALIDATING", progress: 85 },
      VALIDATING: { status: "READY", progress: 100 },
      READY: { status: "READY", progress: 100 },
      FAILED: { status: "FAILED", progress: job.progress },
      EXPIRED: { status: "EXPIRED", progress: job.progress },
    };
    const state = next[job.status];
    if (state.status !== "READY") return { ...job, ...state };
    const spec = this.#specs.get(job.export_job_id);
    const format: ExportFormat = spec?.variants[0]?.format ?? "PNG";
    const extension = format === "LUMI_PACKAGE" ? "lumi.zip" : format === "JPEG" ? "jpg" : format.toLowerCase();
    const mime: Record<ExportFormat, string> = {
      PNG: "image/png", JPEG: "image/jpeg", WEBP: "image/webp", SVG: "image/svg+xml",
      PDF: "application/pdf", ZIP: "application/zip", LUMI_PACKAGE: "application/zip",
    };
    const file = {
      file_id: `${job.export_job_id}-file-1`,
      filename: `summer-launch.${extension}`,
      mime_type: mime[format],
      checksum_sha256: "9e1d77c903e54e44e7d571d9a98e5bf4f6942962880d1d6271b356f05284d934",
      size_bytes: format === "PDF" ? 842331 : 428116,
    };
    return { ...job, ...state, files: [file] };
  }

  #assert(signal?: AbortSignal): void {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  }
}

export function createExportGateway(bootstrap: ExportBootstrap): ExportGateway {
  if (bootstrap.mode === "DETERMINISTIC" && bootstrap.workspace) return new DeterministicExportGateway(bootstrap.workspace);
  return new HttpExportGateway();
}
