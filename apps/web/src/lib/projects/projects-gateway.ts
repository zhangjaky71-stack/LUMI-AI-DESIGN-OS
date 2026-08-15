import { LumiApiClient } from "@/lib/app-shell/api-client";
import {
  normalizeProjectName,
  projectProblem,
  validateCreateProjectInput,
  validateProjectListFilters,
  validateStructuredBrief,
} from "./contracts";
import type {
  AssetScanStatus,
  BriefMutationResult,
  CreateProjectInput,
  CursorPage,
  DeterministicProjectSeed,
  ProjectDetail,
  ProjectListFilters,
  ProjectMutationResult,
  ProjectReference,
  ProjectSummary,
  ProjectsBootstrap,
  RenameProjectInput,
  UpdateBriefInput,
  UploadReferenceInput,
} from "./types";

export interface ProjectsGateway {
  listProjects(
    organizationId: string,
    filters: ProjectListFilters,
    signal?: AbortSignal,
  ): Promise<CursorPage<ProjectSummary>>;
  getProject(
    organizationId: string,
    projectId: string,
    signal?: AbortSignal,
  ): Promise<ProjectDetail>;
  createProject(
    organizationId: string,
    input: CreateProjectInput,
    signal?: AbortSignal,
  ): Promise<ProjectDetail>;
  renameProject(
    organizationId: string,
    input: RenameProjectInput,
    signal?: AbortSignal,
  ): Promise<ProjectMutationResult>;
  archiveProject(
    organizationId: string,
    projectId: string,
    expectedVersion: number,
    signal?: AbortSignal,
  ): Promise<ProjectMutationResult>;
  restoreProject(
    organizationId: string,
    projectId: string,
    expectedVersion: number,
    signal?: AbortSignal,
  ): Promise<ProjectMutationResult>;
  updateBrief(
    organizationId: string,
    input: UpdateBriefInput,
    signal?: AbortSignal,
  ): Promise<BriefMutationResult>;
  uploadReference(
    organizationId: string,
    input: UploadReferenceInput,
    signal?: AbortSignal,
  ): Promise<ProjectReference>;
}

interface UploadSessionResponse {
  readonly upload_id: string;
  readonly asset_id: string;
  readonly upload_url: string;
  readonly headers?: Readonly<Record<string, string>>;
}

interface UploadCompleteResponse {
  readonly asset_id: string;
  readonly scan_status: AssetScanStatus;
  readonly failure_code?: string | null;
}

export class HttpProjectsGateway implements ProjectsGateway {
  readonly #api: LumiApiClient;

  constructor(api: LumiApiClient) {
    this.#api = api;
  }

  listProjects(
    _organizationId: string,
    filters: ProjectListFilters,
    signal?: AbortSignal,
  ): Promise<CursorPage<ProjectSummary>> {
    const safe = validateProjectListFilters(filters);
    const query = new URLSearchParams();
    if (safe.query) query.set("search", safe.query);
    if (safe.status !== "ALL") query.set("status", safe.status);
    if (safe.workspace_id) query.set("workspace_id", safe.workspace_id);
    if (safe.brand_id) query.set("brand_id", safe.brand_id);
    query.set("sort", safe.sort);
    query.set("limit", String(safe.limit));
    if (safe.cursor) query.set("cursor", safe.cursor);
    return this.#api.get<CursorPage<ProjectSummary>>(`/projects?${query.toString()}`, {
      ...(signal ? { signal } : {}),
    });
  }

  getProject(
    _organizationId: string,
    projectId: string,
    signal?: AbortSignal,
  ): Promise<ProjectDetail> {
    return this.#api.get<ProjectDetail>(`/projects/${encodeURIComponent(projectId)}`, {
      ...(signal ? { signal } : {}),
    });
  }

  createProject(
    _organizationId: string,
    input: CreateProjectInput,
    signal?: AbortSignal,
  ): Promise<ProjectDetail> {
    const safe = validateCreateProjectInput(input);
    return this.#api.post<ProjectDetail, Record<string, unknown>>(
      "/projects",
      {
        name: safe.name,
        source_intent: safe.intent,
        brand_id: safe.brand_id,
        deliverables: safe.deliverables,
        default_locale: safe.locale,
        quality_profile: safe.quality_profile,
        budget_microusd: safe.budget_microusd?.toString() ?? null,
      },
      {
        idempotency_key: crypto.randomUUID(),
        ...(signal ? { signal } : {}),
      },
    );
  }

  renameProject(
    _organizationId: string,
    input: RenameProjectInput,
    signal?: AbortSignal,
  ): Promise<ProjectMutationResult> {
    return this.#api.patch<ProjectMutationResult, { name: string }>(
      `/projects/${encodeURIComponent(input.project_id)}`,
      { name: normalizeProjectName(input.name) },
      {
        if_match: String(input.expected_version),
        ...(signal ? { signal } : {}),
      },
    );
  }

  archiveProject(
    _organizationId: string,
    projectId: string,
    expectedVersion: number,
    signal?: AbortSignal,
  ): Promise<ProjectMutationResult> {
    return this.#api.post<ProjectMutationResult, Record<string, never>>(
      `/projects/${encodeURIComponent(projectId)}/archive`,
      {},
      {
        if_match: String(expectedVersion),
        idempotency_key: crypto.randomUUID(),
        ...(signal ? { signal } : {}),
      },
    );
  }

  restoreProject(
    _organizationId: string,
    projectId: string,
    expectedVersion: number,
    signal?: AbortSignal,
  ): Promise<ProjectMutationResult> {
    return this.#api.post<ProjectMutationResult, Record<string, never>>(
      `/projects/${encodeURIComponent(projectId)}/restore`,
      {},
      {
        if_match: String(expectedVersion),
        idempotency_key: crypto.randomUUID(),
        ...(signal ? { signal } : {}),
      },
    );
  }

  updateBrief(
    _organizationId: string,
    input: UpdateBriefInput,
    signal?: AbortSignal,
  ): Promise<BriefMutationResult> {
    const brief = validateStructuredBrief(input.brief);
    return this.#api.patch<BriefMutationResult, Record<string, unknown>>(
      `/projects/${encodeURIComponent(input.project_id)}`,
      {
        brief,
        expected_brief_version: input.expected_brief_version,
      },
      {
        if_match: String(input.expected_project_version),
        ...(signal ? { signal } : {}),
      },
    );
  }

  async uploadReference(
    _organizationId: string,
    input: UploadReferenceInput,
    signal?: AbortSignal,
  ): Promise<ProjectReference> {
    input.on_progress?.(4, "UPLOADING");
    const session = await this.#api.post<UploadSessionResponse, Record<string, unknown>>(
      "/assets/uploads",
      {
        project_id: input.project_id,
        file_name: input.file.name,
        size_bytes: input.file.size,
        content_type: input.file.type || "application/octet-stream",
        reference_role: input.role,
        rights_assertion: "UNKNOWN",
      },
      {
        idempotency_key: crypto.randomUUID(),
        ...(signal ? { signal } : {}),
      },
    );

    input.on_progress?.(18, "UPLOADING");
    await this.#api.putPresignedObject(session.upload_url, input.file, {
      headers: session.headers,
      content_type: input.file.type || "application/octet-stream",
      ...(signal ? { signal } : {}),
    });
    input.on_progress?.(82, "SCANNING");

    const completed = await this.#api.post<
      UploadCompleteResponse,
      { asset_id: string; reference_role: string }
    >(
      `/assets/uploads/${encodeURIComponent(session.upload_id)}/complete`,
      { asset_id: session.asset_id, reference_role: input.role },
      {
        idempotency_key: crypto.randomUUID(),
        ...(signal ? { signal } : {}),
      },
    );

    input.on_progress?.(
      100,
      completed.scan_status === "REJECTED" ? "FAILED" : completed.scan_status === "READY" ? "READY" : "SCANNING",
    );
    return {
      id: `reference:${completed.asset_id}`,
      asset_id: completed.asset_id,
      file_name: input.file.name,
      mime_type: input.file.type || "application/octet-stream",
      size_bytes: input.file.size,
      role: input.role,
      scan_status: completed.scan_status,
      failure_code: completed.failure_code ?? null,
    };
  }
}

function cloneDetail(detail: ProjectDetail): ProjectDetail {
  return structuredClone(detail);
}

function cursorOffset(cursor: string | null): number {
  if (!cursor) return 0;
  const match = /^cursor:(\d+)$/.exec(cursor);
  if (!match?.[1]) throw projectProblem("CURSOR_INVALID", 400);
  return Number(match[1]);
}

function compareProjects(a: ProjectSummary, b: ProjectSummary, sort: ProjectListFilters["sort"]): number {
  if (sort === "name") return a.name.localeCompare(b.name, "zh-CN");
  if (sort === "created") return b.created_at.localeCompare(a.created_at);
  return b.last_activity_at.localeCompare(a.last_activity_at);
}

export class DeterministicProjectsGateway implements ProjectsGateway {
  readonly #projects = new Map<string, ProjectDetail>();
  readonly #renameConflictIds: Set<string>;
  #counter = 100;

  constructor(seed: DeterministicProjectSeed) {
    for (const project of seed.projects) {
      this.#projects.set(project.summary.id, cloneDetail(project));
    }
    this.#renameConflictIds = new Set(seed.rename_conflict_project_ids);
  }

  async listProjects(
    organizationId: string,
    filters: ProjectListFilters,
    signal?: AbortSignal,
  ): Promise<CursorPage<ProjectSummary>> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const safe = validateProjectListFilters(filters);
    const query = safe.query.toLocaleLowerCase("zh-CN");
    const rows = [...this.#projects.values()]
      .map((detail) => detail.summary)
      .filter((project) => project.organization_id === organizationId)
      .filter((project) => safe.status === "ALL" || project.status === safe.status)
      .filter((project) => !safe.workspace_id || project.workspace_id === safe.workspace_id)
      .filter((project) => !safe.brand_id || project.brand?.id === safe.brand_id)
      .filter((project) => !query || project.name.toLocaleLowerCase("zh-CN").includes(query))
      .sort((a, b) => compareProjects(a, b, safe.sort));
    const start = cursorOffset(safe.cursor);
    const items = rows.slice(start, start + safe.limit).map((project) => ({ ...project }));
    const next = start + items.length;
    return {
      items,
      next_cursor: next < rows.length ? `cursor:${next}` : null,
      has_more: next < rows.length,
    };
  }

  async getProject(
    organizationId: string,
    projectId: string,
    signal?: AbortSignal,
  ): Promise<ProjectDetail> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const detail = this.#projects.get(projectId);
    if (!detail || detail.summary.organization_id !== organizationId) {
      throw projectProblem("PROJECT_NOT_FOUND", 404);
    }
    return cloneDetail(detail);
  }

  async createProject(
    organizationId: string,
    input: CreateProjectInput,
    signal?: AbortSignal,
  ): Promise<ProjectDetail> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const safe = validateCreateProjectInput(input);
    this.#counter += 1;
    const id = `project-e2e-${this.#counter}`;
    const now = new Date(Date.UTC(2026, 7, 15, 1, 0, this.#counter % 60)).toISOString();
    const summary: ProjectSummary = {
      id,
      organization_id: organizationId,
      workspace_id: organizationId === "org-northstar" ? "workspace-northstar" : "workspace-lumi",
      name: safe.name ?? safe.intent.slice(0, 42),
      status: "ACTIVE",
      version: 1,
      created_at: now,
      last_activity_at: now,
      brand: safe.brand_id && safe.brand_name ? { id: safe.brand_id, name: safe.brand_name } : null,
      active_run_count: 0,
      artifact_count: 0,
      preview_label: "Brief ready",
    };
    const brief = validateStructuredBrief({
      objective: safe.intent,
      audience: "待 Brief Agent 进一步确认",
      deliverables: safe.deliverables,
      constraints: [],
      assumptions: ["当前结构化 Brief 来自确定性 E2E adapter，生产由 Brief Agent 生成。"],
      locale: safe.locale,
      brand_context: safe.brand_name,
      notes: "",
    });
    const detail: ProjectDetail = {
      summary,
      brief_version: 1,
      brief,
      brief_history: [{ version: 1, created_at: now, brief }],
      references: [],
    };
    this.#projects.set(id, detail);
    return cloneDetail(detail);
  }

  async renameProject(
    organizationId: string,
    input: RenameProjectInput,
    signal?: AbortSignal,
  ): Promise<ProjectMutationResult> {
    const detail = await this.getProject(organizationId, input.project_id, signal);
    if (detail.summary.version !== input.expected_version) throw projectProblem("VERSION_CONFLICT");
    if (this.#renameConflictIds.delete(input.project_id)) throw projectProblem("VERSION_CONFLICT");
    const next: ProjectSummary = {
      ...detail.summary,
      name: normalizeProjectName(input.name),
      version: detail.summary.version + 1,
      last_activity_at: new Date(Date.UTC(2026, 7, 15, 2, 0, detail.summary.version)).toISOString(),
    };
    this.#projects.set(input.project_id, { ...detail, summary: next });
    return { project: { ...next } };
  }

  async archiveProject(
    organizationId: string,
    projectId: string,
    expectedVersion: number,
    signal?: AbortSignal,
  ): Promise<ProjectMutationResult> {
    const detail = await this.getProject(organizationId, projectId, signal);
    if (detail.summary.version !== expectedVersion) throw projectProblem("VERSION_CONFLICT");
    const next: ProjectSummary = {
      ...detail.summary,
      status: "ARCHIVED",
      version: detail.summary.version + 1,
      active_run_count: 0,
    };
    this.#projects.set(projectId, { ...detail, summary: next });
    return { project: { ...next } };
  }

  async restoreProject(
    organizationId: string,
    projectId: string,
    expectedVersion: number,
    signal?: AbortSignal,
  ): Promise<ProjectMutationResult> {
    const detail = await this.getProject(organizationId, projectId, signal);
    if (detail.summary.version !== expectedVersion) throw projectProblem("VERSION_CONFLICT");
    const next: ProjectSummary = {
      ...detail.summary,
      status: "ACTIVE",
      version: detail.summary.version + 1,
      active_run_count: 0,
    };
    this.#projects.set(projectId, { ...detail, summary: next });
    return { project: { ...next } };
  }

  async updateBrief(
    organizationId: string,
    input: UpdateBriefInput,
    signal?: AbortSignal,
  ): Promise<BriefMutationResult> {
    const detail = await this.getProject(organizationId, input.project_id, signal);
    if (
      detail.summary.version !== input.expected_project_version ||
      detail.brief_version !== input.expected_brief_version
    ) {
      throw projectProblem("VERSION_CONFLICT");
    }
    const brief = validateStructuredBrief(input.brief);
    const briefVersion = detail.brief_version + 1;
    const now = new Date(Date.UTC(2026, 7, 15, 3, briefVersion, 0)).toISOString();
    const project = {
      ...detail.summary,
      version: detail.summary.version + 1,
      last_activity_at: now,
    };
    this.#projects.set(input.project_id, {
      ...detail,
      summary: project,
      brief,
      brief_version: briefVersion,
      brief_history: [...detail.brief_history, { version: briefVersion, created_at: now, brief }],
    });
    return { project: { ...project }, brief_version: briefVersion, brief };
  }

  async uploadReference(
    organizationId: string,
    input: UploadReferenceInput,
    signal?: AbortSignal,
  ): Promise<ProjectReference> {
    const detail = await this.getProject(organizationId, input.project_id, signal);
    input.on_progress?.(12, "UPLOADING");
    await Promise.resolve();
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    input.on_progress?.(76, "SCANNING");
    await Promise.resolve();

    const rejected = /scan-fail|malware/i.test(input.file.name);
    const assetId = `asset-e2e-${++this.#counter}`;
    const reference: ProjectReference = {
      id: `reference:${assetId}`,
      asset_id: assetId,
      file_name: input.file.name,
      mime_type: input.file.type || "application/octet-stream",
      size_bytes: input.file.size,
      role: input.role,
      scan_status: rejected ? "REJECTED" : "READY",
      failure_code: rejected ? "SCAN_FAILED" : null,
    };
    input.on_progress?.(100, rejected ? "FAILED" : "READY");
    const project = {
      ...detail.summary,
      version: detail.summary.version + 1,
      last_activity_at: new Date(Date.UTC(2026, 7, 15, 4, this.#counter % 60, 0)).toISOString(),
    };
    this.#projects.set(input.project_id, {
      ...detail,
      summary: project,
      references: [...detail.references, reference],
    });
    return { ...reference };
  }
}

let deterministicGateway: DeterministicProjectsGateway | null = null;
let deterministicSeedKey = "";

function seedKey(seed: DeterministicProjectSeed): string {
  return seed.projects.map((project) => project.summary.id).join("|");
}

export function getProjectsGateway(
  api: LumiApiClient,
  bootstrap: ProjectsBootstrap,
): ProjectsGateway {
  if (bootstrap.mode !== "e2e") return new HttpProjectsGateway(api);
  if (!bootstrap.seed) throw new Error("PROJECTS_E2E_SEED_REQUIRED");
  const key = seedKey(bootstrap.seed);
  if (!deterministicGateway || deterministicSeedKey !== key) {
    deterministicGateway = new DeterministicProjectsGateway(bootstrap.seed);
    deterministicSeedKey = key;
  }
  return deterministicGateway;
}

export function resetDeterministicProjectsGatewayForTests(): void {
  deterministicGateway = null;
  deterministicSeedKey = "";
}
