import { ExportDownloadService, ExportEngine } from "./export-engine";
import type { ExportJob, ExportJobRepository, ExportSpec } from "./export-engine-types";

export interface CreateExportResponse {
  readonly export_job_id: string;
  readonly status: ExportJob["status"];
  readonly progress: number;
  readonly artifact_version_id: string;
  readonly design_document_version_id: string;
  readonly export_fingerprint: string;
}

export interface ExportStatusResponse extends CreateExportResponse {
  readonly files: readonly {
    readonly file_id: string;
    readonly filename: string;
    readonly mime_type: string;
    readonly checksum_sha256: string;
    readonly size_bytes: number;
  }[];
  readonly error_code?: string;
}

function response(job: ExportJob): CreateExportResponse {
  return {
    export_job_id: job.export_job_id,
    status: job.status,
    progress: job.progress,
    artifact_version_id: job.source.artifact_version_id,
    design_document_version_id: job.source.design_document_version_id,
    export_fingerprint: job.export_fingerprint,
  };
}

export class ExportApiFacade {
  readonly #engine: ExportEngine;
  readonly #jobs: ExportJobRepository;
  readonly #downloads: ExportDownloadService;

  constructor(args: { readonly engine: ExportEngine; readonly jobs: ExportJobRepository; readonly downloads: ExportDownloadService }) {
    this.#engine = args.engine;
    this.#jobs = args.jobs;
    this.#downloads = args.downloads;
  }

  async createExport(spec: ExportSpec): Promise<CreateExportResponse> {
    return response(await this.#engine.start(spec));
  }

  async runExport(args: { readonly organization_id: string; readonly export_job_id: string }): Promise<ExportStatusResponse> {
    return this.#status(await this.#engine.execute(args.organization_id, args.export_job_id));
  }

  async getExport(args: { readonly organization_id: string; readonly export_job_id: string }): Promise<ExportStatusResponse> {
    const job = await this.#jobs.get(args.organization_id, args.export_job_id);
    if (!job) throw new Error("EXPORT_JOB_NOT_FOUND");
    return this.#status(job);
  }

  async getDownload(args: {
    readonly organization_id: string;
    readonly actor_id: string;
    readonly export_job_id: string;
    readonly file_id: string;
    readonly expires_seconds?: number;
  }): Promise<{ readonly url: string; readonly expires_at: string; readonly filename: string }> {
    return this.#downloads.download(args);
  }

  #status(job: ExportJob): ExportStatusResponse {
    return {
      ...response(job),
      files: [...job.files, ...(job.manifest_file ? [job.manifest_file] : [])].map((file) => ({
        file_id: file.file_id,
        filename: file.filename,
        mime_type: file.mime_type,
        checksum_sha256: file.checksum_sha256,
        size_bytes: file.size_bytes,
      })),
      ...(job.error_code ? { error_code: job.error_code } : {}),
    };
  }
}
