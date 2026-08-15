import { Collaboration } from "@/components/collaboration/collaboration";
import { getCollaborationBootstrap } from "@/lib/collaboration/collaboration-server";

export const dynamic = "force-dynamic";

export default async function CollaborationPage({
  params,
}: Readonly<{ params: Promise<{ projectId: string }> }>) {
  const { projectId } = await params;
  return <Collaboration projectId={projectId} bootstrap={getCollaborationBootstrap(projectId)} />;
}
