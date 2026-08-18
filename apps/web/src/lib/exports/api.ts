import { api } from "@/lib/api/client";
import {
  parseExportCapabilities,
  parseExportDownloadGrant,
  parseExportJob,
  type ExportCapabilities,
  type ExportDownloadGrant,
  type ExportFormat,
  type ExportJob,
} from "@/lib/exports/types";
import { tenantHeaders } from "@/lib/workspace/api";

export async function getExportCapabilities(
  organizationId: string,
  projectId: string,
  artifactVersionId: string,
): Promise<ExportCapabilities> {
  const payload = await api.get<unknown>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/artifact-versions/${encodeURIComponent(artifactVersionId)}/export-capabilities`,
    { headers: tenantHeaders(organizationId) },
  );
  return parseExportCapabilities(payload);
}

export async function createExportTask(
  organizationId: string,
  projectId: string,
  artifactVersionIds: readonly string[],
): Promise<string> {
  const payload = await api.post<unknown>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/tasks`,
    {
      task_type: "export",
      name: artifactVersionIds.length > 1 ? `Export ${artifactVersionIds.length} artifacts` : "Export artifact",
      dependency_ids: [],
      priority: 0,
      max_attempts: 3,
      input: { artifact_version_ids: [...artifactVersionIds] },
    },
    {
      headers: {
        ...tenantHeaders(organizationId),
        "Idempotency-Key": crypto.randomUUID(),
      },
    },
  );
  const record = asRecord(payload, "EXPORT_TASK_INVALID");
  return requiredString(record.id, "EXPORT_TASK_ID_REQUIRED");
}

export async function createExportJob(
  organizationId: string,
  projectId: string,
  taskId: string,
  items: readonly { artifactVersionId: string; targetFormat: ExportFormat; outputName: string }[],
): Promise<ExportJob> {
  const payload = await api.post<unknown>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/export-jobs`,
    {
      task_id: taskId,
      items: items.map((item) => ({
        artifact_version_id: item.artifactVersionId,
        target_format: item.targetFormat,
        output_name: item.outputName,
      })),
      force_zip: items.length > 1,
      package_name: items.length > 1 ? "lumi-export" : safePackageName(items[0]?.outputName ?? "export"),
    },
    {
      headers: {
        ...tenantHeaders(organizationId),
        "Idempotency-Key": crypto.randomUUID(),
      },
    },
  );
  return parseExportJob(payload);
}

export async function getExportJob(organizationId: string, jobId: string): Promise<ExportJob> {
  const payload = await api.get<unknown>(`/api/v1/export-jobs/${encodeURIComponent(jobId)}`, {
    headers: tenantHeaders(organizationId),
  });
  return parseExportJob(payload);
}

export async function cancelExportJob(organizationId: string, jobId: string): Promise<ExportJob> {
  const payload = await api.post<unknown>(
    `/api/v1/export-jobs/${encodeURIComponent(jobId)}/cancel`,
    undefined,
    { headers: tenantHeaders(organizationId) },
  );
  return parseExportJob(payload);
}

export async function issueExportDownload(organizationId: string, jobId: string): Promise<ExportDownloadGrant> {
  const payload = await api.post<unknown>(
    `/api/v1/export-jobs/${encodeURIComponent(jobId)}/download-grants`,
    undefined,
    { headers: tenantHeaders(organizationId) },
  );
  return parseExportDownloadGrant(payload);
}

function safePackageName(value: string): string {
  const withoutExtension = value.replace(/\.[A-Za-z0-9]{1,8}$/, "");
  const safe = withoutExtension.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
  return safe || "export";
}
function asRecord(value: unknown, code: string): Record<string, unknown> { if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(code); return value as Record<string, unknown>; }
function requiredString(value: unknown, code: string): string { if (typeof value !== "string" || !value.trim()) throw new Error(code); return value; }
