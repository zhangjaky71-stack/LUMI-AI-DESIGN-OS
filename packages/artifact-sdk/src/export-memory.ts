import type {
  ExportArtifactPort,
  ExportAuthorizationPort,
  ExportDownloadAuditPort,
  ExportDownloadSignerPort,
  ExportEventPort,
  ExportJob,
  ExportJobRepository,
  ExportObjectStore,
  ExportSourcePort,
  ExportSourceSnapshot,
  ExportSpec,
  ExportValidationEvidencePort,
} from "./export-engine-types";
import type { StoredObjectStat } from "./types";

async function sha256(bytes: Uint8Array): Promise<string> {
  const copy = Uint8Array.from(bytes);
  const digest = await crypto.subtle.digest("SHA-256", copy.buffer);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

export class InMemoryExportJobRepository implements ExportJobRepository {
  readonly byId = new Map<string, ExportJob>();
  readonly byOperation = new Map<string, ExportJob>();

  async findByOperation(organizationId: string, operationId: string): Promise<ExportJob | null> {
    return this.byOperation.get(`${organizationId}:${operationId}`) ?? null;
  }

  async findReadyByFingerprint(organizationId: string, fingerprint: string, minimumExpiresAtIso: string): Promise<ExportJob | null> {
    for (const job of this.byId.values()) {
      if (job.organization_id === organizationId && job.export_fingerprint === fingerprint && job.status === "READY" && job.expires_at >= minimumExpiresAtIso) return job;
    }
    return null;
  }

  async get(organizationId: string, exportJobId: string): Promise<ExportJob | null> {
    const job = this.byId.get(exportJobId);
    return job?.organization_id === organizationId ? job : null;
  }

  async save(job: ExportJob): Promise<void> {
    const operationKey = `${job.organization_id}:${job.operation_id}`;
    const existing = this.byOperation.get(operationKey);
    if (existing && existing.export_fingerprint !== job.export_fingerprint) throw new Error("EXPORT_OPERATION_SEMANTIC_CONFLICT");
    this.byId.set(job.export_job_id, job);
    this.byOperation.set(operationKey, job);
  }
}

export class StaticExportSource implements ExportSourcePort {
  readonly snapshots = new Map<string, ExportSourceSnapshot>();
  resolve_count = 0;

  add(snapshot: ExportSourceSnapshot): void {
    this.snapshots.set(`${snapshot.organization_id}:${snapshot.artifact_version_id}:${snapshot.design_document_version_id}`, snapshot);
  }

  async resolveExactSnapshot(spec: ExportSpec): Promise<ExportSourceSnapshot> {
    this.resolve_count += 1;
    const snapshot = this.snapshots.get(`${spec.organization_id}:${spec.artifact_version_id}:${spec.design_document_version_id}`);
    if (!snapshot) throw new Error("EXPORT_EXACT_SOURCE_NOT_FOUND");
    return snapshot;
  }
}

export class InMemoryExportObjectStore implements ExportObjectStore {
  readonly objects = new Map<string, Uint8Array>();
  readonly mimeTypes = new Map<string, string>();
  put_count = 0;

  async put(storageKey: string, payload: Uint8Array, mimeType: string): Promise<{ storage_key: string; checksum_sha256: string; size_bytes: number }> {
    if (!storageKey || storageKey.includes("://") || storageKey.includes("..")) throw new Error("EXPORT_STORAGE_KEY_UNSAFE");
    if (!mimeType) throw new Error("EXPORT_STORAGE_MIME_REQUIRED");
    this.put_count += 1;
    const bytes = Uint8Array.from(payload);
    this.objects.set(storageKey, bytes);
    this.mimeTypes.set(storageKey, mimeType);
    return { storage_key: storageKey, checksum_sha256: await sha256(bytes), size_bytes: bytes.length };
  }

  async get(storageKey: string): Promise<Uint8Array> {
    const bytes = this.objects.get(storageKey);
    if (!bytes) throw new Error("EXPORT_STORAGE_OBJECT_NOT_FOUND");
    return Uint8Array.from(bytes);
  }

  async stat(storageKey: string): Promise<StoredObjectStat | null> {
    const bytes = this.objects.get(storageKey);
    if (!bytes) return null;
    const mimeType = this.mimeTypes.get(storageKey);
    return { storage_key: storageKey, size_bytes: bytes.length, checksum_sha256: await sha256(bytes), ...(mimeType ? { mime_type: mimeType } : {}) };
  }
}

export class RecordingExportArtifacts implements ExportArtifactPort {
  readonly persisted: Array<Parameters<ExportArtifactPort["persistExport"]>[0]> = [];
  async persistExport(args: Parameters<ExportArtifactPort["persistExport"]>[0]): Promise<void> { this.persisted.push(args) }
}

export class RecordingExportEvents implements ExportEventPort {
  readonly events: Array<{ type: string; payload: Readonly<Record<string, unknown>> }> = [];
  async emit(eventType: string, payload: Readonly<Record<string, unknown>>): Promise<void> { this.events.push({ type: eventType, payload }) }
}

export class RecordingExportValidationEvidence implements ExportValidationEvidencePort {
  readonly records: Array<Parameters<ExportValidationEvidencePort["record"]>[0]> = [];
  async record(args: Parameters<ExportValidationEvidencePort["record"]>[0]): Promise<void> { this.records.push(args) }
}

export class StaticExportAuthorization implements ExportAuthorizationPort {
  constructor(readonly allowed: boolean) {}
  async canDownload(): Promise<boolean> { return this.allowed }
}

export class RecordingExportDownloadAudit implements ExportDownloadAuditPort {
  readonly records: Array<Parameters<ExportDownloadAuditPort["record"]>[0]> = [];
  async record(args: Parameters<ExportDownloadAuditPort["record"]>[0]): Promise<void> { this.records.push(args) }
}

export class RecordingExportSigner implements ExportDownloadSignerPort {
  readonly calls: Array<{ storage_key: string; filename: string; expires_seconds: number }> = [];
  async sign(args: { readonly storage_key: string; readonly filename: string; readonly expires_seconds: number }): Promise<{ url: string; expires_at: string }> {
    this.calls.push({ ...args });
    return { url: `https://signed.invalid/${encodeURIComponent(args.storage_key)}?ttl=${args.expires_seconds}`, expires_at: new Date(Date.parse("2030-01-01T00:00:00.000Z") + args.expires_seconds * 1000).toISOString() };
  }
}
