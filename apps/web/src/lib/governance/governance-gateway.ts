import { LumiApiClient, LumiApiError } from "@/lib/app-shell/api-client";
import type {
  AuditDownloadLeaseView,
  AuditExportJobView,
  AuditFilters,
  AuditPageView,
  DeletionView,
  ExportFormat,
  GovernanceBootstrap,
  GovernanceCapabilities,
  GovernanceWorkspace,
  LegalHoldView,
  RetentionPolicyView,
} from "./types";

export interface GovernanceGateway {
  load(signal?: AbortSignal): Promise<GovernanceWorkspace>;
  searchAudit(filters: AuditFilters, signal?: AbortSignal): Promise<AuditPageView>;
  publishRetention(retentionClass: string, version: number, retentionDays: number, note: string): Promise<RetentionPolicyView>;
  createHold(scopeType: string, scopeId: string, reasonCode: string, ticketRef: string): Promise<LegalHoldView>;
  releaseHold(holdId: string, reasonCode: string, ticketRef: string): Promise<LegalHoldView>;
  requestDeletion(subjectUserId: string): Promise<DeletionView>;
  executeDeletion(requestId: string): Promise<DeletionView>;
  createExport(format: ExportFormat, filters: AuditFilters): Promise<AuditExportJobView>;
  getDownload(jobId: string): Promise<AuditDownloadLeaseView>;
}

interface AuditExportRequest {
  readonly export_format: ExportFormat;
  readonly action: string | undefined;
  readonly result: string | undefined;
  readonly resource_type: string | undefined;
  readonly resource_id: string | undefined;
  readonly trace_id: string | undefined;
}

function request(signal?: AbortSignal): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

function queryString(filters: AuditFilters): string {
  const params = new URLSearchParams();
  if (filters.action) params.set("action", filters.action);
  if (filters.result) params.set("result", filters.result);
  if (filters.resource_type) params.set("resource_type", filters.resource_type);
  if (filters.resource_id) params.set("resource_id", filters.resource_id);
  if (filters.trace_id) params.set("trace_id", filters.trace_id);
  if (filters.cursor) params.set("cursor", filters.cursor);
  params.set("limit", "50");
  return params.toString();
}

async function optionalScope<T>(promise: Promise<T>, fallback: T): Promise<T> {
  try {
    return await promise;
  } catch (error) {
    if (error instanceof LumiApiError && error.problem.status === 403) return fallback;
    throw error;
  }
}

class HttpGovernanceGateway implements GovernanceGateway {
  constructor(private readonly api: LumiApiClient, private readonly organizationId: string) {}

  async load(signal?: AbortSignal): Promise<GovernanceWorkspace> {
    const options = request(signal);
    const [capabilities, audit] = await Promise.all([
      this.api.get<GovernanceCapabilities>("/governance/capabilities", options),
      this.api.get<AuditPageView>("/governance/audit?limit=50", options),
    ]);
    const [policies, candidates, holds, deletions, exports] = await Promise.all([
      optionalScope(
        this.api.get<{ items: GovernanceWorkspace["retention_policies"] }>("/governance/retention/policies", options),
        { items: [] },
      ),
      optionalScope(
        this.api.get<{ items: GovernanceWorkspace["retention_candidates"] }>("/governance/retention/candidates", options),
        { items: [] },
      ),
      optionalScope(
        this.api.get<{ items: GovernanceWorkspace["legal_holds"] }>("/governance/legal-holds", options),
        { items: [] },
      ),
      optionalScope(
        this.api.get<{ items: GovernanceWorkspace["deletions"] }>("/governance/deletions", options),
        { items: [] },
      ),
      optionalScope(
        this.api.get<{ items: GovernanceWorkspace["exports"] }>("/governance/audit/exports", options),
        { items: [] },
      ),
    ]);
    return {
      organization_id: this.organizationId,
      capabilities,
      audit,
      retention_policies: policies.items,
      retention_candidates: candidates.items,
      legal_holds: holds.items,
      deletions: deletions.items,
      exports: exports.items,
    };
  }

  searchAudit(filters: AuditFilters, signal?: AbortSignal): Promise<AuditPageView> {
    return this.api.get<AuditPageView>(`/governance/audit?${queryString(filters)}`, request(signal));
  }

  publishRetention(retentionClass: string, version: number, retentionDays: number, note: string): Promise<RetentionPolicyView> {
    return this.api.post<RetentionPolicyView, { retention_class: string; version: number; retention_days: number; policy_note: string }>(
      "/governance/retention/policies",
      { retention_class: retentionClass, version, retention_days: retentionDays, policy_note: note },
    );
  }

  createHold(scopeType: string, scopeId: string, reasonCode: string, ticketRef: string): Promise<LegalHoldView> {
    return this.api.post<LegalHoldView, { hold_type: "LEGAL"; organization_id: string; scope_type: string; scope_id: string; reason_code: string; ticket_ref: string }>(
      "/governance/legal-holds",
      {
        hold_type: "LEGAL",
        organization_id: this.organizationId,
        scope_type: scopeType,
        scope_id: scopeId,
        reason_code: reasonCode,
        ticket_ref: ticketRef,
      },
    );
  }

  releaseHold(holdId: string, reasonCode: string, ticketRef: string): Promise<LegalHoldView> {
    return this.api.post<LegalHoldView, { reason_code: string; ticket_ref: string }>(
      `/governance/legal-holds/${encodeURIComponent(holdId)}:release`,
      { reason_code: reasonCode, ticket_ref: ticketRef },
    );
  }

  requestDeletion(subjectUserId: string): Promise<DeletionView> {
    return this.api.post<DeletionView, { subject_user_id: string; organization_id: string; reason_code: string }>(
      "/governance/deletions",
      {
        subject_user_id: subjectUserId,
        organization_id: this.organizationId,
        reason_code: "DATA_SUBJECT_REQUEST",
      },
    );
  }

  executeDeletion(requestId: string): Promise<DeletionView> {
    return this.api.post<DeletionView, Record<string, never>>(
      `/governance/deletions/${encodeURIComponent(requestId)}:execute`,
      {},
    );
  }

  createExport(format: ExportFormat, filters: AuditFilters): Promise<AuditExportJobView> {
    const body: AuditExportRequest = {
      export_format: format,
      action: filters.action,
      result: filters.result,
      resource_type: filters.resource_type,
      resource_id: filters.resource_id,
      trace_id: filters.trace_id,
    };
    return this.api.post<AuditExportJobView, AuditExportRequest>("/governance/audit/exports", body);
  }

  getDownload(jobId: string): Promise<AuditDownloadLeaseView> {
    return this.api.post<AuditDownloadLeaseView, Record<string, never>>(
      `/governance/audit/exports/${encodeURIComponent(jobId)}:download?ttl_seconds=300`,
      {},
    );
  }
}

class DeterministicGovernanceGateway implements GovernanceGateway {
  private workspace: GovernanceWorkspace;
  private leaseCounter = 0;

  constructor(workspace: GovernanceWorkspace) {
    this.workspace = structuredClone(workspace);
  }

  async load(signal?: AbortSignal): Promise<GovernanceWorkspace> {
    this.abort(signal);
    return structuredClone(this.workspace);
  }

  async searchAudit(filters: AuditFilters, signal?: AbortSignal): Promise<AuditPageView> {
    this.abort(signal);
    let items = [...this.workspace.audit.items];
    if (filters.action) items = items.filter((item) => item.action.includes(filters.action ?? ""));
    if (filters.result) items = items.filter((item) => item.result === filters.result);
    if (filters.resource_type) items = items.filter((item) => item.resource_type === filters.resource_type);
    if (filters.resource_id) items = items.filter((item) => item.resource_id.includes(filters.resource_id ?? ""));
    if (filters.trace_id) items = items.filter((item) => item.trace_id === filters.trace_id);
    const start = filters.cursor ? Number.parseInt(filters.cursor.replace("cursor-", ""), 10) || 0 : 0;
    const page = items.slice(start, start + 2);
    const nextCursor = start + 2 < items.length ? `cursor-${start + 2}` : null;
    return { items: page, next_cursor: nextCursor };
  }

  async publishRetention(retentionClass: string, version: number, retentionDays: number, note: string): Promise<RetentionPolicyView> {
    if (!this.workspace.capabilities.can_manage_retention) throw new Error("GOVERNANCE_FORBIDDEN");
    const policy: RetentionPolicyView = {
      retention_class: retentionClass as RetentionPolicyView["retention_class"],
      version,
      retention_days: retentionDays,
      created_by: "security-e2e",
      created_at: new Date().toISOString(),
      policy_note: note,
    };
    this.workspace = { ...this.workspace, retention_policies: [...this.workspace.retention_policies, policy] };
    return policy;
  }

  async createHold(scopeType: string, scopeId: string, reasonCode: string, ticketRef: string): Promise<LegalHoldView> {
    if (!this.workspace.capabilities.can_manage_holds) throw new Error("GOVERNANCE_FORBIDDEN");
    const hold: LegalHoldView = {
      hold_id: `hold-e2e-${this.workspace.legal_holds.length + 1}`,
      hold_type: "LEGAL",
      organization_id: this.workspace.organization_id,
      scope_type: scopeType as LegalHoldView["scope_type"],
      scope_id: scopeId,
      reason_code: reasonCode,
      ticket_ref: ticketRef,
      created_by: "security-e2e",
      created_at: new Date().toISOString(),
    };
    this.workspace = { ...this.workspace, legal_holds: [hold, ...this.workspace.legal_holds] };
    return hold;
  }

  async releaseHold(holdId: string): Promise<LegalHoldView> {
    const hold = this.workspace.legal_holds.find((item) => item.hold_id === holdId);
    if (!hold) throw new Error("LEGAL_HOLD_NOT_ACTIVE");
    this.workspace = {
      ...this.workspace,
      legal_holds: this.workspace.legal_holds.filter((item) => item.hold_id !== holdId),
    };
    return hold;
  }

  async requestDeletion(subjectUserId: string): Promise<DeletionView> {
    if (!this.workspace.capabilities.can_manage_deletion) throw new Error("GOVERNANCE_FORBIDDEN");
    const matchingHolds = this.workspace.legal_holds.filter(
      (item) => item.scope_type === "USER" && item.scope_id === subjectUserId,
    );
    const value: DeletionView = {
      request_id: `delete-e2e-${this.workspace.deletions.length + 1}`,
      subject_user_id: subjectUserId,
      organization_id: this.workspace.organization_id,
      status: matchingHolds.length ? "BLOCKED_HOLD" : "REQUESTED",
      resource_refs: ["ASSET:asset-e2e", "PROFILE:profile-e2e", "AUDIT_EVENT:audit-retained"],
      blocked_hold_ids: matchingHolds.map((item) => item.hold_id),
      deleted_count: 0,
      anonymized_count: 0,
      retained_count: 0,
      error_code: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    this.workspace = { ...this.workspace, deletions: [value, ...this.workspace.deletions] };
    return value;
  }

  async executeDeletion(requestId: string): Promise<DeletionView> {
    const current = this.workspace.deletions.find((item) => item.request_id === requestId);
    if (!current) throw new Error("DELETION_REQUEST_NOT_FOUND");
    const matchingHolds = this.workspace.legal_holds.filter(
      (item) => item.scope_type === "USER" && item.scope_id === current.subject_user_id,
    );
    const updated: DeletionView = matchingHolds.length
      ? {
          ...current,
          status: "BLOCKED_HOLD",
          blocked_hold_ids: matchingHolds.map((item) => item.hold_id),
          updated_at: new Date().toISOString(),
        }
      : {
          ...current,
          status: "COMPLETED",
          blocked_hold_ids: [],
          deleted_count: 1,
          anonymized_count: 1,
          retained_count: 1,
          updated_at: new Date().toISOString(),
        };
    this.workspace = {
      ...this.workspace,
      deletions: this.workspace.deletions.map((item) => item.request_id === requestId ? updated : item),
    };
    return updated;
  }

  async createExport(format: ExportFormat): Promise<AuditExportJobView> {
    if (!this.workspace.capabilities.can_export_audit) throw new Error("GOVERNANCE_FORBIDDEN");
    const job: AuditExportJobView = {
      job_id: `audit-export-e2e-${this.workspace.exports.length + 1}`,
      organization_id: this.workspace.organization_id,
      export_format: format,
      status: "READY",
      created_by: "org-owner-e2e",
      created_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
      object_ref: "audit-export://immutable/events",
      file_name: `lumi-audit-e2e.${format === "JSON" ? "json" : "csv"}`,
      checksum_sha256: "65".repeat(32),
      size_bytes: 2048,
      error_code: null,
    };
    this.workspace = { ...this.workspace, exports: [job, ...this.workspace.exports] };
    return job;
  }

  async getDownload(jobId: string): Promise<AuditDownloadLeaseView> {
    const job = this.workspace.exports.find((item) => item.job_id === jobId);
    if (!job || job.status !== "READY") throw new Error("AUDIT_EXPORT_NOT_READY");
    this.leaseCounter += 1;
    return {
      job_id: jobId,
      signed_url: `https://audit-download.invalid/${this.leaseCounter}/${jobId}?sig=ephemeral`,
      expires_at: new Date(Date.now() + 300_000).toISOString(),
    };
  }

  private abort(signal?: AbortSignal): void {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  }
}

export function createGovernanceGateway(
  bootstrap: GovernanceBootstrap,
  api: LumiApiClient,
  organizationId: string,
): GovernanceGateway {
  if (bootstrap.mode === "DETERMINISTIC" && bootstrap.workspace) {
    return new DeterministicGovernanceGateway(bootstrap.workspace);
  }
  return new HttpGovernanceGateway(api, organizationId);
}
