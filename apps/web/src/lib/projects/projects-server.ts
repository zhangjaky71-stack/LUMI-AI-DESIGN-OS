import type {
  DeterministicProjectSeed,
  ProjectDetail,
  ProjectStatus,
  ProjectsBootstrap,
  StructuredBrief,
} from "./types";

function brief(
  objective: string,
  locale = "zh-CN",
  deliverables: readonly string[] = ["社交媒体视觉"],
): StructuredBrief {
  return {
    objective,
    audience: "品牌现有用户与潜在新客",
    deliverables,
    constraints: ["保持品牌识别一致", "所有关键文字保持清晰可读"],
    assumptions: ["E2E seed：生产 Structured Brief 由 NODE-17/Brief Agent 持久化。"],
    locale,
    brand_context: null,
    notes: "",
  };
}

function project(
  options: {
    readonly id: string;
    readonly organization_id: string;
    readonly workspace_id: string;
    readonly name: string;
    readonly status: ProjectStatus;
    readonly activity: string;
    readonly created: string;
    readonly brand?: { readonly id: string; readonly name: string } | null;
    readonly artifact_count?: number;
    readonly active_run_count?: number;
    readonly preview_label?: string;
    readonly objective?: string;
    readonly deliverables?: readonly string[];
  },
): ProjectDetail {
  const structured = brief(
    options.objective ?? `为“${options.name}”建立清晰的设计方向。`,
    "zh-CN",
    options.deliverables,
  );
  return {
    summary: {
      id: options.id,
      organization_id: options.organization_id,
      workspace_id: options.workspace_id,
      name: options.name,
      status: options.status,
      version: 3,
      created_at: options.created,
      last_activity_at: options.activity,
      brand: options.brand ?? null,
      active_run_count: options.active_run_count ?? 0,
      artifact_count: options.artifact_count ?? 0,
      preview_label: options.preview_label ?? "Design workspace",
    },
    brief_version: 2,
    brief: structured,
    brief_history: [
      {
        version: 1,
        created_at: options.created,
        brief: { ...structured, assumptions: ["初始 Brief"] },
      },
      { version: 2, created_at: options.activity, brief: structured },
    ],
    references: [],
  };
}

const E2E_SEED: DeterministicProjectSeed = {
  projects: [
    project({
      id: "project-summer-launch",
      organization_id: "org-lumi",
      workspace_id: "workspace-lumi",
      name: "夏季新品发布",
      status: "ACTIVE",
      activity: "2026-08-15T00:58:00.000Z",
      created: "2026-08-10T02:00:00.000Z",
      brand: { id: "brand-lumi", name: "LUMI Coffee" },
      artifact_count: 18,
      active_run_count: 1,
      preview_label: "Campaign · 4:5",
      deliverables: ["主视觉", "社交媒体视觉", "门店海报"],
    }),
    project({
      id: "project-menu-refresh",
      organization_id: "org-lumi",
      workspace_id: "workspace-lumi",
      name: "秋季菜单更新",
      status: "DRAFT",
      activity: "2026-08-14T08:20:00.000Z",
      created: "2026-08-13T05:00:00.000Z",
      brand: { id: "brand-lumi", name: "LUMI Coffee" },
      artifact_count: 3,
      preview_label: "Menu · A4",
    }),
    project({
      id: "project-conflict",
      organization_id: "org-lumi",
      workspace_id: "workspace-lumi",
      name: "门店物料升级",
      status: "ACTIVE",
      activity: "2026-08-13T09:10:00.000Z",
      created: "2026-08-01T05:00:00.000Z",
      brand: { id: "brand-field", name: "Field Notes" },
      artifact_count: 9,
      preview_label: "Retail kit",
    }),
    project({
      id: "project-social-weekly",
      organization_id: "org-lumi",
      workspace_id: "workspace-lumi",
      name: "社媒周更视觉",
      status: "ACTIVE",
      activity: "2026-08-12T11:00:00.000Z",
      created: "2026-07-18T03:00:00.000Z",
      brand: { id: "brand-field", name: "Field Notes" },
      artifact_count: 26,
      preview_label: "Social · 1:1",
    }),
    project({
      id: "project-brand-guide",
      organization_id: "org-lumi",
      workspace_id: "workspace-lumi",
      name: "品牌手册补充",
      status: "PAUSED",
      activity: "2026-08-09T06:00:00.000Z",
      created: "2026-07-04T04:00:00.000Z",
      brand: { id: "brand-lumi", name: "LUMI Coffee" },
      artifact_count: 12,
      preview_label: "Brand system",
    }),
    project({
      id: "project-product-scenes",
      organization_id: "org-lumi",
      workspace_id: "workspace-lumi",
      name: "产品场景图批次",
      status: "ACTIVE",
      activity: "2026-08-08T04:00:00.000Z",
      created: "2026-08-03T04:00:00.000Z",
      brand: { id: "brand-lumi", name: "LUMI Coffee" },
      artifact_count: 31,
      active_run_count: 2,
      preview_label: "Product scene",
    }),
    project({
      id: "project-packaging",
      organization_id: "org-lumi",
      workspace_id: "workspace-lumi",
      name: "包装标签探索",
      status: "DRAFT",
      activity: "2026-08-07T04:00:00.000Z",
      created: "2026-08-07T03:00:00.000Z",
      brand: null,
      artifact_count: 1,
      preview_label: "Packaging",
    }),
    project({
      id: "project-archive-demo",
      organization_id: "org-lumi",
      workspace_id: "workspace-lumi",
      name: "春季活动归档",
      status: "ARCHIVED",
      activity: "2026-06-22T04:00:00.000Z",
      created: "2026-03-02T03:00:00.000Z",
      brand: { id: "brand-lumi", name: "LUMI Coffee" },
      artifact_count: 44,
      preview_label: "Archived campaign",
    }),
    project({
      id: "project-editorial",
      organization_id: "org-lumi",
      workspace_id: "workspace-studio",
      name: "编辑部封面系列",
      status: "ACTIVE",
      activity: "2026-08-06T03:00:00.000Z",
      created: "2026-07-29T03:00:00.000Z",
      brand: null,
      artifact_count: 6,
      preview_label: "Editorial",
    }),
    project({
      id: "project-northstar-1",
      organization_id: "org-northstar",
      workspace_id: "workspace-northstar",
      name: "Northstar Launch Kit",
      status: "ACTIVE",
      activity: "2026-08-15T00:30:00.000Z",
      created: "2026-08-11T00:00:00.000Z",
      brand: { id: "brand-northstar", name: "Northstar" },
      artifact_count: 7,
      preview_label: "Launch kit",
      objective: "Prepare a focused launch visual system for Northstar.",
    }),
    project({
      id: "project-northstar-2",
      organization_id: "org-northstar",
      workspace_id: "workspace-northstar",
      name: "Northstar Product Cards",
      status: "DRAFT",
      activity: "2026-08-12T00:30:00.000Z",
      created: "2026-08-12T00:00:00.000Z",
      brand: { id: "brand-northstar", name: "Northstar" },
      artifact_count: 0,
      preview_label: "Product cards",
    }),
  ],
  rename_conflict_project_ids: ["project-conflict"],
};

export function getProjectsBootstrap(): ProjectsBootstrap {
  const e2e =
    process.env.NODE_ENV !== "production" && process.env.LUMI_PROJECTS_E2E === "1";
  if (!e2e) {
    return {
      mode: "http",
      page_size: 8,
      brand_options: [],
      workspace_options: [],
      seed: null,
    };
  }

  return {
    mode: "e2e",
    page_size: 4,
    brand_options: [
      { id: "brand-lumi", name: "LUMI Coffee" },
      { id: "brand-field", name: "Field Notes" },
      { id: "brand-northstar", name: "Northstar" },
    ],
    workspace_options: [
      { id: "workspace-lumi", name: "LUMI Studio" },
      { id: "workspace-studio", name: "Editorial Studio" },
      { id: "workspace-northstar", name: "Northstar Workspace" },
    ],
    seed: E2E_SEED,
  };
}
