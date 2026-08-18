import Link from "next/link";
import { redirect } from "next/navigation";

import { AiWorkspace } from "@/components/workspace/ai-workspace";
import { requireAppSession } from "@/lib/auth/session";
import { getProject } from "@/lib/projects/api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  project?: string | string[];
  run?: string | string[];
}>;

export default async function WorkspacePage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const projectId = scalar(params.project);
  const runId = scalar(params.run);
  if (!projectId) redirect("/projects/dashboard");

  const [session, project] = await Promise.all([
    requireAppSession(),
    getProject(projectId),
  ]);

  return (
    <div className="workspace-route-shell">
      <div className="workspace-breadcrumb-row">
        <Link href="/projects/dashboard">Projects</Link>
        <span aria-hidden="true">/</span>
        <Link href={`/projects/${encodeURIComponent(project.id)}`}>{project.name}</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">AI Workspace</span>
      </div>
      <AiWorkspace
        organizationId={session.organization.id}
        project={{
          id: project.id,
          name: project.name,
          objective: project.brief?.objective ?? null,
          deliverables: project.brief?.deliverables ?? [],
          constraints: project.brief?.constraints ?? [],
        }}
        initialRunId={runId}
      />
    </div>
  );
}

function scalar(value: string | string[] | undefined): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed || null;
}
