export type ProjectStatus =
  | "DRAFT"
  | "ACTIVE"
  | "PAUSED"
  | "COMPLETED"
  | "ARCHIVED"
  | string;

export type ProjectSummary = {
  id: string;
  name: string;
  status: ProjectStatus;
  version?: number | null;
  workspaceId?: string | null;
  brandId?: string | null;
  description?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
};

export type ProjectBrief = {
  objective?: string | null;
  audience?: string | null;
  deliverables: readonly string[];
  constraints: readonly string[];
};

export type ProjectDetail = ProjectSummary & {
  brief?: ProjectBrief | null;
};

export type CreateProjectInput = {
  name: string;
  description?: string;
  objective?: string;
  audience?: string;
  deliverables: readonly string[];
  constraints: readonly string[];
};

export function parseProjectSummary(value: unknown): ProjectSummary {
  const record = requireRecord(value, "PROJECT_PAYLOAD_INVALID");
  return {
    id: requireString(record.id, "PROJECT_ID_REQUIRED"),
    name: requireString(record.name, "PROJECT_NAME_REQUIRED"),
    status: optionalString(record.status)?.toUpperCase() ?? "DRAFT",
    version: optionalInteger(record.version),
    workspaceId: optionalString(record.workspaceId ?? record.workspace_id),
    brandId: optionalString(record.brandId ?? record.brand_id),
    description: optionalString(record.description),
    createdAt: optionalString(record.createdAt ?? record.created_at),
    updatedAt: optionalString(record.updatedAt ?? record.updated_at),
  };
}

export function parseProjectDetail(value: unknown): ProjectDetail {
  const summary = parseProjectSummary(value);
  const record = requireRecord(value, "PROJECT_PAYLOAD_INVALID");
  const briefValue = record.brief;
  if (briefValue === undefined || briefValue === null) return summary;
  const brief = requireRecord(briefValue, "PROJECT_BRIEF_INVALID");
  return {
    ...summary,
    brief: {
      objective: optionalString(brief.objective),
      audience: optionalString(brief.audience ?? brief.target_audience),
      deliverables: stringArray(brief.deliverables),
      constraints: stringArray(brief.constraints),
    },
  };
}

export function parseProjectCollection(value: unknown): readonly ProjectSummary[] {
  const candidates = Array.isArray(value)
    ? value
    : isRecord(value)
      ? value.items ?? value.projects ?? value.results
      : undefined;
  if (!Array.isArray(candidates)) throw new Error("PROJECT_LIST_PAYLOAD_INVALID");
  return candidates.map(parseProjectSummary);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function requireRecord(value: unknown, code: string): Record<string, unknown> { if (!isRecord(value)) throw new Error(code); return value; }
function requireString(value: unknown, code: string): string { if (typeof value !== "string" || !value.trim()) throw new Error(code); return value; }
function optionalString(value: unknown): string | null | undefined { if (value === undefined || value === null) return value; if (typeof value !== "string") return undefined; return value; }
function optionalInteger(value: unknown): number | null | undefined { if (value === undefined || value === null) return value; return Number.isInteger(value) && (value as number) >= 1 ? value as number : undefined; }
function stringArray(value: unknown): readonly string[] { if (!Array.isArray(value)) return []; return value.filter((item): item is string => typeof item === "string"); }
