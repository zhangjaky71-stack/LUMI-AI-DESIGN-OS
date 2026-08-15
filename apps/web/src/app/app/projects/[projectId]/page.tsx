import Link from "next/link";
import { ProjectDetail } from "@/components/projects/project-detail";
import workspaceStyles from "@/components/ai-workspace/ai-workspace.module.css";
import { getProjectsBootstrap } from "@/lib/projects/projects-server";

export const dynamic = "force-dynamic";

export default async function ProjectPage({
  params,
}: Readonly<{
  params: Promise<{ projectId: string }>;
}>) {
  const { projectId } = await params;
  return (
    <div className={workspaceStyles.projectWithWorkspaceEntry}>
      <div className={workspaceStyles.workspaceEntry}>
        <span>自然语言 + Canvas + Approval + immutable history + governed export</span>
        <div>
          <Link href={`/app/projects/${encodeURIComponent(projectId)}/workspace`}>
            进入 AI Workspace →
          </Link>
          {" · "}
          <Link href={`/app/projects/${encodeURIComponent(projectId)}/versions`}>
            Versions →
          </Link>
          {" · "}
          <Link href={`/app/projects/${encodeURIComponent(projectId)}/export`}>
            Export →
          </Link>
        </div>
      </div>
      <ProjectDetail projectId={projectId} bootstrap={getProjectsBootstrap()} />
    </div>
  );
}
