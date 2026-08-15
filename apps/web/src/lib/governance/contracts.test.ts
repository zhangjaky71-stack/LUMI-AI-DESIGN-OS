import { describe, expect, it } from "vitest";
import { canDownload, latestRetentionPolicies, safeAuditDownloadUrl } from "./contracts";
import type { AuditExportJobView, RetentionPolicyView } from "./types";

describe("governance contracts", () => {
  it("selects latest immutable retention policy versions", () => {
    const policies: RetentionPolicyView[] = [
      { retention_class: "CONTENT", version: 1, retention_days: 365, created_by: "system", created_at: "2026-01-01T00:00:00Z", policy_note: "v1" },
      { retention_class: "CONTENT", version: 2, retention_days: 90, created_by: "security", created_at: "2026-08-01T00:00:00Z", policy_note: "v2" },
      { retention_class: "SECURITY_AUDIT", version: 1, retention_days: 2555, created_by: "system", created_at: "2026-01-01T00:00:00Z", policy_note: "v1" },
    ];
    const latest = latestRetentionPolicies(policies);
    expect(latest.find((item) => item.retention_class === "CONTENT")?.version).toBe(2);
  });

  it("accepts only HTTPS signed download leases", () => {
    expect(safeAuditDownloadUrl({ job_id: "j", signed_url: "https://download.invalid/j?sig=x", expires_at: "2026-08-15T00:00:00Z" })).toContain("https://");
    expect(safeAuditDownloadUrl({ job_id: "j", signed_url: "javascript:alert(1)", expires_at: "2026-08-15T00:00:00Z" })).toBeNull();
  });

  it("fails closed unless an audit export is READY with immutable file metadata", () => {
    const base: AuditExportJobView = {
      job_id: "j", organization_id: "org-a", export_format: "JSON", status: "READY",
      created_by: "u", created_at: "2026-08-15T00:00:00Z", completed_at: "2026-08-15T00:01:00Z",
      object_ref: "audit-export://j/events.json", file_name: "events.json", checksum_sha256: "a".repeat(64), size_bytes: 10, error_code: null,
    };
    expect(canDownload(base)).toBe(true);
    expect(canDownload({ ...base, status: "RUNNING" })).toBe(false);
    expect(canDownload({ ...base, checksum_sha256: null })).toBe(false);
  });
});
