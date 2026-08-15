import { ExportUI } from "@/components/export-ui/export-ui";
import { getExportBootstrap } from "@/lib/export-ui/export-server";

export const dynamic = "force-dynamic";

export default async function ExportPage({
  params,
}: Readonly<{ params: Promise<{ projectId: string }> }>) {
  const { projectId } = await params;
  return <ExportUI projectId={projectId} bootstrap={getExportBootstrap(projectId)} />;
}
