export type AuditResult = "SUCCESS" | "DENIED" | "FAILED";
export type RetentionClass =
  | "SECURITY_AUDIT"
  | "BILLING"
  | "CONTENT"
  | "AGENT_TRACE"
  | "TEMP_SANDBOX"
  | "EXPORT"
  | "ANALYTICS";
export type ExportFormat = "JSON" | "CSV";
export type ExportStatus = "PENDING" | "RUNNING" | "READY" | "FAILED" | "EXPIRED";

export interface GovernanceCapabilities {
  readonly can_read_audit: boolean;
  readonly can_export_audit: boolean;
  readonly can_manage_retention: boolean;
  readonly can_manage_holds: boolean;
  readonly can_manage_deletion: boolean;
}

export interface AuditEventView {
  readonly event_id: string;
  readonly organization_id: string | null;
  readonly actor_type: "USER" | "PLATFORM_ADMIN" | "AGENT" | "SERVICE";
  readonly actor_id: string;
  readonly actor_version: string | null;
  readonly action: string;
  readonly resource_type: string;
  readonly resource_id: string;
  readonly resource_version: string | null;
  readonly result: AuditResult;
  readonly reason_code: string;
  readonly request_id: string | null;
  readonly trace_id: string | null;
  readonly retention_class: RetentionClass;
  readonly retention_policy_version: number;
  readonly correction_of_event_id: string | null;
  readonly occurred_at: string;
  readonly event_hash: string;
}

export interface AuditPageView {
  readonly items: readonly AuditEventView[];
  readonly next_cursor: string | null;
}

export interface RetentionPolicyView {
  readonly retention_class: RetentionClass;
  readonly version: number;
  readonly retention_days: number;
  readonly created_by: string;
  readonly created_at: string;
  readonly policy_note: string;
}

export interface RetentionCandidateView {
  readonly resource: {
    readonly resource_type: string;
    readonly resource_id: string;
    readonly organization_id: string;
    readonly retention_class: RetentionClass;
    readonly created_at: string;
    readonly subject_user_id: string | null;
    readonly erasure_mode: "DELETE" | "ANONYMIZE" | "RETENTION_ONLY";
  };
  readonly policy_version: number;
  readonly eligible_at: string;
}

export interface LegalHoldView {
  readonly hold_id: string;
  readonly hold_type: "LEGAL" | "BILLING";
  readonly organization_id: string | null;
  readonly scope_type: "USER" | "ORGANIZATION" | "RESOURCE" | "RETENTION_CLASS";
  readonly scope_id: string;
  readonly reason_code: string;
  readonly ticket_ref: string;
  readonly created_by: string;
  readonly created_at: string;
}

export interface DeletionView {
  readonly request_id: string;
  readonly subject_user_id: string;
  readonly organization_id: string;
  readonly status: "REQUESTED" | "BLOCKED_HOLD" | "DEACTIVATED" | "DELETING" | "COMPLETED" | "FAILED";
  readonly resource_refs: readonly string[];
  readonly blocked_hold_ids: readonly string[];
  readonly deleted_count: number;
  readonly anonymized_count: number;
  readonly retained_count: number;
  readonly error_code: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface AuditExportJobView {
  readonly job_id: string;
  readonly organization_id: string | null;
  readonly export_format: ExportFormat;
  readonly status: ExportStatus;
  readonly created_by: string;
  readonly created_at: string;
  readonly completed_at: string | null;
  readonly object_ref: string | null;
  readonly file_name: string | null;
  readonly checksum_sha256: string | null;
  readonly size_bytes: number | null;
  readonly error_code: string | null;
}

export interface AuditDownloadLeaseView {
  readonly job_id: string;
  readonly signed_url: string;
  readonly expires_at: string;
}

export interface GovernanceWorkspace {
  readonly organization_id: string;
  readonly capabilities: GovernanceCapabilities;
  readonly audit: AuditPageView;
  readonly retention_policies: readonly RetentionPolicyView[];
  readonly retention_candidates: readonly RetentionCandidateView[];
  readonly legal_holds: readonly LegalHoldView[];
  readonly deletions: readonly DeletionView[];
  readonly exports: readonly AuditExportJobView[];
}

export interface GovernanceBootstrap {
  readonly mode: "HTTP" | "DETERMINISTIC";
  readonly workspace: GovernanceWorkspace | null;
}

export interface AuditFilters {
  readonly action?: string | undefined;
  readonly result?: AuditResult | undefined;
  readonly resource_type?: string | undefined;
  readonly resource_id?: string | undefined;
  readonly trace_id?: string | undefined;
  readonly cursor?: string | undefined;
}
