import { AIWorkspace } from "@/components/ai-workspace/ai-workspace";
import { getAIWorkspaceBootstrap } from "@/lib/ai-workspace/workspace-server";
import { getInfiniteCanvasBootstrap } from "@/lib/infinite-canvas/canvas-server";

export const dynamic = "force-dynamic";

export default async function AIWorkspacePage({
  params,
}: Readonly<{
  params: Promise<{ projectId: string }>;
}>) {
  const { projectId } = await params;
  return (
    <AIWorkspace
      projectId={projectId}
      bootstrap={getAIWorkspaceBootstrap(projectId)}
      canvasBootstrap={getInfiniteCanvasBootstrap(projectId)}
    />
  );
}
