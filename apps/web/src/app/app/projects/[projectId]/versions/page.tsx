import { VersionsUI } from "@/components/versions-ui/versions-ui";
import { getVersionsBootstrap } from "@/lib/versions-ui/versions-server";

export const dynamic = "force-dynamic";

export default async function VersionsPage({
  params,
}: Readonly<{
  params: Promise<{ projectId: string }>;
}>) {
  const { projectId } = await params;
  return <VersionsUI projectId={projectId} bootstrap={getVersionsBootstrap(projectId)} />;
}
