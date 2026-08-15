import { ProjectDetail } from "@/components/projects/project-detail";
import { getProjectsBootstrap } from "@/lib/projects/projects-server";

export const dynamic = "force-dynamic";

export default async function ProjectPage({
  params,
}: Readonly<{
  params: Promise<{ projectId: string }>;
}>) {
  const { projectId } = await params;
  return <ProjectDetail projectId={projectId} bootstrap={getProjectsBootstrap()} />;
}
