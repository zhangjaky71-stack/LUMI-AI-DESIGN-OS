export type ProjectStatus = "DRAFT" | "ACTIVE" | "PAUSED" | "ARCHIVED";
export type ProjectSort = "recent" | "name" | "created";
export type ProjectsViewMode = "grid" | "list";

export type ReferenceRole =
  | "product"
  | "logo"
  | "style_reference"
  | "content_reference"
  | "brand_guide"
  | "other";

export type AssetScanStatus = "QUEUED" | "SCANNING" | "READY" | "REJECTED";
export type UploadUiStatus = "LOCAL" | "UPLOADING" | "SCANNING" | "READY" | "FAILED";

export interface ProjectBrandSummary {
  readonly id: string;
  readonly name: string;
}

export interface ProjectSummary {
  readonly id: string;
  readonly organization_id: string;
  readonly workspace_id: string;
  readonly name: string;
  readonly status: ProjectStatus;
  readonly version: number;
  readonly created_at: string;
  readonly last_activity_at: string;
  readonly brand: ProjectBrandSummary | null;
  readonly active_run_count: number;
  readonly artifact_count: number;
  readonly preview_label: string | null;
}

export interface ProjectListFilters {
  readonly query: string;
  readonly status: ProjectStatus | "ALL";
  readonly workspace_id: string | null;
  readonly brand_id: string | null;
  readonly sort: ProjectSort;
  readonly cursor: string | null;
  readonly limit: number;
}

export interface CursorPage<T> {
  readonly items: readonly T[];
  readonly next_cursor: string | null;
  readonly has_more: boolean;
}

export interface ProjectReference {
  readonly id: string;
  readonly asset_id: string;
  readonly file_name: string;
  readonly mime_type: string;
  readonly size_bytes: number;
  readonly role: ReferenceRole;
  readonly scan_status: AssetScanStatus;
  readonly failure_code: string | null;
}

export interface StagedReference {
  readonly client_id: string;
  readonly file: File;
  readonly role: ReferenceRole;
  readonly ui_status: UploadUiStatus;
  readonly progress: number;
  readonly asset_id: string | null;
  readonly failure_code: string | null;
}

export interface StructuredBrief {
  readonly objective: string;
  readonly audience: string;
  readonly deliverables: readonly string[];
  readonly constraints: readonly string[];
  readonly assumptions: readonly string[];
  readonly locale: string;
  readonly brand_context: string | null;
  readonly notes: string;
}

export interface BriefVersion {
  readonly version: number;
  readonly created_at: string;
  readonly brief: StructuredBrief;
}

export interface ProjectDetail {
  readonly summary: ProjectSummary;
  readonly brief_version: number;
  readonly brief: StructuredBrief;
  readonly brief_history: readonly BriefVersion[];
  readonly references: readonly ProjectReference[];
}

export interface CreateProjectInput {
  readonly intent: string;
  readonly name: string | null;
  readonly brand_id: string | null;
  readonly brand_name: string | null;
  readonly deliverables: readonly string[];
  readonly locale: string;
  readonly quality_profile: string | null;
  readonly budget_microusd: bigint | null;
}

export interface RenameProjectInput {
  readonly project_id: string;
  readonly name: string;
  readonly expected_version: number;
}

export interface UpdateBriefInput {
  readonly project_id: string;
  readonly expected_project_version: number;
  readonly expected_brief_version: number;
  readonly brief: StructuredBrief;
}

export interface UploadReferenceInput {
  readonly project_id: string;
  readonly file: File;
  readonly role: ReferenceRole;
  readonly on_progress?: (progress: number, status: UploadUiStatus) => void;
}

export interface ProjectMutationResult {
  readonly project: ProjectSummary;
}

export interface BriefMutationResult {
  readonly project: ProjectSummary;
  readonly brief_version: number;
  readonly brief: StructuredBrief;
}

export interface ProjectBrandOption {
  readonly id: string;
  readonly name: string;
}

export interface ProjectWorkspaceOption {
  readonly id: string;
  readonly name: string;
}

export interface DeterministicProjectSeed {
  readonly projects: readonly ProjectDetail[];
  readonly rename_conflict_project_ids: readonly string[];
}

export interface ProjectsBootstrap {
  readonly mode: "http" | "e2e";
  readonly page_size: number;
  readonly brand_options: readonly ProjectBrandOption[];
  readonly workspace_options: readonly ProjectWorkspaceOption[];
  readonly seed: DeterministicProjectSeed | null;
}

export const DEFAULT_PROJECT_FILTERS: ProjectListFilters = {
  query: "",
  status: "ALL",
  workspace_id: null,
  brand_id: null,
  sort: "recent",
  cursor: null,
  limit: 8,
};

export const REFERENCE_ROLE_LABELS: Readonly<Record<ReferenceRole, string>> = {
  product: "产品",
  logo: "Logo",
  style_reference: "风格参考",
  content_reference: "内容参考",
  brand_guide: "品牌指南",
  other: "其他",
};
