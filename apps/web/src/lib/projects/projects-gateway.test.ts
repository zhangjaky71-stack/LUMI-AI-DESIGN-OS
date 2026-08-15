import { describe, expect, it } from "vitest";
import { DeterministicProjectsGateway } from "./projects-gateway";
import type {
  DeterministicProjectSeed,
  ProjectDetail,
  StructuredBrief,
} from "./types";

function brief(objective: string): StructuredBrief {
  return {
    objective,
    audience: "Audience",
    deliverables: ["Poster"],
    constraints: [],
    assumptions: [],
    locale: "zh-CN",
    brand_context: null,
    notes: "",
  };
}

function detail(
  id: string,
  organizationId: string,
  name: string,
  status: "ACTIVE" | "ARCHIVED" = "ACTIVE",
): ProjectDetail {
  const value = brief(`Objective ${name}`);
  return {
    summary: {
      id,
      organization_id: organizationId,
      workspace_id: `workspace-${organizationId}`,
      name,
      status,
      version: 1,
      created_at: "2026-08-01T00:00:00.000Z",
      last_activity_at: `2026-08-${id.endsWith("3") ? "13" : id.endsWith("2") ? "12" : "11"}T00:00:00.000Z`,
      brand: null,
      active_run_count: status === "ARCHIVED" ? 0 : 1,
      artifact_count: 2,
      preview_label: "Fixture",
    },
    brief_version: 1,
    brief: value,
    brief_history: [
      {
        version: 1,
        created_at: "2026-08-01T00:00:00.000Z",
        brief: value,
      },
    ],
    references: [],
  };
}

function seed(): DeterministicProjectSeed {
  return {
    projects: [
      detail("project-1", "org-a", "Alpha"),
      detail("project-2", "org-a", "Beta"),
      detail("project-3", "org-a", "Gamma"),
      detail("project-other", "org-b", "Other"),
      detail("project-archive", "org-a", "Archive", "ARCHIVED"),
    ],
    rename_conflict_project_ids: ["project-2"],
  };
}

const filters = {
  query: "",
  status: "ALL" as const,
  workspace_id: null,
  brand_id: null,
  sort: "recent" as const,
  cursor: null,
  limit: 2,
};

describe("DeterministicProjectsGateway", () => {
  it("paginates with an opaque cursor and never crosses organizations", async () => {
    const gateway = new DeterministicProjectsGateway(seed());
    const first = await gateway.listProjects("org-a", filters);
    expect(first.items).toHaveLength(2);
    expect(
      first.items.every((project) => project.organization_id === "org-a"),
    ).toBe(true);
    expect(first.has_more).toBe(true);

    const second = await gateway.listProjects("org-a", {
      ...filters,
      cursor: first.next_cursor,
    });
    expect(
      second.items.every((project) => project.organization_id === "org-a"),
    ).toBe(true);
    expect(
      new Set([...first.items, ...second.items].map((project) => project.id))
        .size,
    ).toBe(4);
  });

  it("creates a project from only a natural-language intent and optional brand context", async () => {
    const gateway = new DeterministicProjectsGateway(seed());
    const created = await gateway.createProject("org-a", {
      intent: "做一套高级极简的新品咖啡发布视觉",
      name: null,
      brand_id: "brand-1",
      brand_name: "LUMI Coffee",
      deliverables: [],
      locale: "zh-CN",
      quality_profile: null,
      budget_microusd: null,
    });
    expect(created.summary.name).toContain("高级极简");
    expect(created.summary.brand?.name).toBe("LUMI Coffee");
    expect(created.brief.objective).toContain("新品咖啡");
    expect(created.brief_version).toBe(1);
  });

  it("raises a real VERSION_CONFLICT before a stale rename can be accepted", async () => {
    const gateway = new DeterministicProjectsGateway(seed());
    await expect(
      gateway.renameProject("org-a", {
        project_id: "project-2",
        name: "Beta renamed",
        expected_version: 1,
      }),
    ).rejects.toMatchObject({
      problem: { code: "VERSION_CONFLICT" },
    });

    const unchanged = await gateway.getProject("org-a", "project-2");
    expect(unchanged.summary.name).toBe("Beta");
  });

  it("archives and restores without resurrecting historical active runs", async () => {
    const gateway = new DeterministicProjectsGateway(seed());
    const archived = await gateway.archiveProject("org-a", "project-1", 1);
    expect(archived.project.status).toBe("ARCHIVED");
    expect(archived.project.active_run_count).toBe(0);

    const restored = await gateway.restoreProject(
      "org-a",
      "project-1",
      archived.project.version,
    );
    expect(restored.project.status).toBe("ACTIVE");
    expect(restored.project.active_run_count).toBe(0);
  });

  it("keeps a rejected scanner result explicit instead of marking the upload ready", async () => {
    const gateway = new DeterministicProjectsGateway(seed());
    const progress: string[] = [];
    const reference = await gateway.uploadReference("org-a", {
      project_id: "project-1",
      file: new File(["fixture"], "scan-fail-logo.png", {
        type: "image/png",
      }),
      role: "logo",
      on_progress: (value, status) => progress.push(`${status}:${value}`),
    });
    expect(reference.scan_status).toBe("REJECTED");
    expect(reference.failure_code).toBe("SCAN_FAILED");
    expect(progress.at(-1)).toBe("FAILED:100");
  });

  it("creates a new BriefVersion rather than mutating history in place", async () => {
    const gateway = new DeterministicProjectsGateway(seed());
    const current = await gateway.getProject("org-a", "project-1");
    const result = await gateway.updateBrief("org-a", {
      project_id: "project-1",
      expected_project_version: current.summary.version,
      expected_brief_version: current.brief_version,
      brief: { ...current.brief, objective: "Updated objective" },
    });
    expect(result.brief_version).toBe(2);

    const after = await gateway.getProject("org-a", "project-1");
    expect(after.brief_history).toHaveLength(2);
    expect(after.brief_history[0]?.brief.objective).toBe("Objective Alpha");
    expect(after.brief.objective).toBe("Updated objective");
  });
});
