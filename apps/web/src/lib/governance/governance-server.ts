import type { ShellSession } from "@/lib/app-shell/types";
import type { GovernanceBootstrap, GovernanceWorkspace } from "./types";

const NODE65_FIXTURE_MARKER = "node65_governance_fixture_v1";

function deterministicWorkspace(organizationId: string): GovernanceWorkspace {
  void NODE65_FIXTURE_MARKER;
  const now = "2026-08-15T08:00:00.000Z";
  return {
    organization_id: organizationId,
    capabilities: {
      can_read_audit: true,
      can_export_audit: true,
      can_manage_retention: true,
      can_manage_holds: true,
      can_manage_deletion: true,
    },
    audit: {
      items: [
        {
          event_id: "audit-node65-4",
          organization_id: organizationId,
          actor_type: "PLATFORM_ADMIN",
          actor_id: "ops-e2e",
          actor_version: null,
          action: "ADMIN_QUEUE_REQUEUED",
          resource_type: "QUEUE_ITEM",
          resource_id: "queue-e2e-1",
          resource_version: null,
          result: "SUCCESS",
          reason_code: "INCIDENT_RECOVERY",
          request_id: "req-node65-4",
          trace_id: "trace-node65",
          retention_class: "SECURITY_AUDIT",
          retention_policy_version: 1,
          correction_of_event_id: null,
          occurred_at: now,
          event_hash: "4".repeat(64),
        },
        {
          event_id: "audit-node65-3",
          organization_id: organizationId,
          actor_type: "AGENT",
          actor_id: "designer-agent",
          actor_version: "v7",
          action: "TOOL_WRITE_EXTERNAL",
          resource_type: "TOOL_CALL",
          resource_id: "tool-call-node65",
          resource_version: "web.publish@2.1.0",
          result: "SUCCESS",
          reason_code: "APPROVED_WRITE",
          request_id: "req-node65-3",
          trace_id: "trace-node65",
          retention_class: "AGENT_TRACE",
          retention_policy_version: 1,
          correction_of_event_id: null,
          occurred_at: "2026-08-15T07:50:00.000Z",
          event_hash: "3".repeat(64),
        },
        {
          event_id: "audit-node65-2",
          organization_id: organizationId,
          actor_type: "USER",
          actor_id: "user-e2e",
          actor_version: null,
          action: "ARTIFACT_APPROVED",
          resource_type: "ARTIFACT_VERSION",
          resource_id: "artifact-node65-v4",
          resource_version: "v4",
          result: "SUCCESS",
          reason_code: "APPROVED",
          request_id: "req-node65-2",
          trace_id: "trace-artifact-65",
          retention_class: "CONTENT",
          retention_policy_version: 1,
          correction_of_event_id: null,
          occurred_at: "2026-08-15T07:40:00.000Z",
          event_hash: "2".repeat(64),
        },
        {
          event_id: "audit-node65-1",
          organization_id: organizationId,
          actor_type: "USER",
          actor_id: "user-e2e",
          actor_version: null,
          action: "PROJECT_ARCHIVED",
          resource_type: "PROJECT",
          resource_id: "project-summer-launch",
          resource_version: null,
          result: "DENIED",
          reason_code: "INSUFFICIENT_PERMISSION",
          request_id: "req-node65-1",
          trace_id: "trace-project-65",
          retention_class: "SECURITY_AUDIT",
          retention_policy_version: 1,
          correction_of_event_id: null,
          occurred_at: "2026-08-15T07:30:00.000Z",
          event_hash: "1".repeat(64),
        },
      ],
      next_cursor: null,
    },
    retention_policies: [
      ["SECURITY_AUDIT", 2555],
      ["BILLING", 2555],
      ["CONTENT", 365],
      ["AGENT_TRACE", 90],
      ["TEMP_SANDBOX", 7],
      ["EXPORT", 30],
      ["ANALYTICS", 400],
    ].map(([retention_class, retention_days]) => ({
      retention_class: retention_class as GovernanceWorkspace["retention_policies"][number]["retention_class"],
      version: 1,
      retention_days: retention_days as number,
      created_by: "system:node-65-default",
      created_at: now,
      policy_note: "Engineering default; legal review required before production launch.",
    })),
    retention_candidates: [
      {
        resource: {
          resource_type: "TEMP_SANDBOX",
          resource_id: "sandbox-old-65",
          organization_id: organizationId,
          retention_class: "TEMP_SANDBOX",
          created_at: "2026-07-01T00:00:00.000Z",
          subject_user_id: "user-e2e",
          erasure_mode: "DELETE",
        },
        policy_version: 1,
        eligible_at: "2026-07-08T00:00:00.000Z",
      },
    ],
    legal_holds: [],
    deletions: [],
    exports: [
      {
        job_id: "audit-export-node65-ready",
        organization_id: organizationId,
        export_format: "JSON",
        status: "READY",
        created_by: "user-e2e",
        created_at: "2026-08-15T07:20:00.000Z",
        completed_at: "2026-08-15T07:21:00.000Z",
        object_ref: "audit-export://audit-export-node65-ready/events.json",
        file_name: "lumi-audit-node65.json",
        checksum_sha256: "65".repeat(32),
        size_bytes: 4096,
        error_code: null,
      },
    ],
  };
}

export function getGovernanceBootstrap(session: ShellSession): GovernanceBootstrap {
  if (process.env.NODE_ENV !== "production" && process.env.LUMI_GOVERNANCE_E2E === "1") {
    return {
      mode: "DETERMINISTIC",
      workspace: deterministicWorkspace(session.active_organization_id),
    };
  }
  return { mode: "HTTP", workspace: null };
}
