import { serverApiRequest } from "@/lib/api/server";
import {
  type CreateProjectInput,
  type ProjectDetail,
  type ProjectSummary,
  parseProjectCollection,
  parseProjectDetail,
} from "@/lib/projects/types";

const PROJECTS_PATH = "/api/v1/projects";

export async function listProjects(): Promise<readonly ProjectSummary[]> {
  const payload = await serverApiRequest<unknown>(PROJECTS_PATH, {
    method: "GET",
  });
  return parseProjectCollection(payload);
}

export async function getProject(projectId: string): Promise<ProjectDetail> {
  const payload = await serverApiRequest<unknown>(projectPath(projectId), {
    method: "GET",
  });
  return parseProjectDetail(payload);
}

export async function createProject(
  input: CreateProjectInput,
  operationId: string,
): Promise<ProjectDetail> {
  const payload = await serverApiRequest<unknown>(PROJECTS_PATH, {
    method: "POST",
    headers: {
      "Idempotency-Key": operationId,
    },
    json: {
      name: input.name,
      ...(input.description ? { description: input.description } : {}),
      brief: {
        ...(input.objective ? { objective: input.objective } : {}),
        ...(input.audience ? { audience: input.audience } : {}),
        deliverables: input.deliverables,
        constraints: input.constraints,
      },
    },
  });
  return parseProjectDetail(payload);
}

export function projectPath(projectId: string): string {
  if (!projectId.trim()) throw new Error("PROJECT_ID_REQUIRED");
  return `${PROJECTS_PATH}/${encodeURIComponent(projectId)}`;
}
