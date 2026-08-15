import { AIWorkspace } from "@/components/ai-workspace/ai-workspace";
import { getAIWorkspaceBootstrap } from "@/lib/ai-workspace/workspace-server";
import { getInfiniteCanvasBootstrap } from "@/lib/infinite-canvas/canvas-server";

export const dynamic = "force-dynamic";

function first(value: string | string[] | undefined): string | null {
  return Array.isArray(value) ? value[0] ?? null : value ?? null;
}

export default async function AIWorkspacePage({
  params,
  searchParams,
}: Readonly<{
  params: Promise<{ projectId: string }>;
  searchParams: Promise<{ focusNode?: string | string[]; brandRuleVersion?: string | string[] }>;
}>) {
  const { projectId } = await params;
  const query = await searchParams;
  return (
    <AIWorkspace
      projectId={projectId}
      bootstrap={getAIWorkspaceBootstrap(projectId)}
      canvasBootstrap={getInfiniteCanvasBootstrap(projectId)}
      focusNodeId={first(query.focusNode)}
      requestedBrandRuleVersion={first(query.brandRuleVersion)}
    />
  );
}
