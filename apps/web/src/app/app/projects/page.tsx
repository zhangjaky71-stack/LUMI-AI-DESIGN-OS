import { ProjectsDashboard } from "@/components/projects/projects-dashboard";
import { getProjectsBootstrap } from "@/lib/projects/projects-server";

export const dynamic = "force-dynamic";

export default function ProjectsPage() {
  return <ProjectsDashboard bootstrap={getProjectsBootstrap()} />;
}
