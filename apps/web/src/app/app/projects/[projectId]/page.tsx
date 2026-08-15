import { ShellSection } from "@/components/app-shell/shell-section";

export default async function ProjectPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return (
    <ShellSection
      eyebrow="PROJECT WORKSPACE"
      title={`项目 ${projectId}`}
      description="项目级 Agent Workspace、Infinite Canvas 与版本面板会在后续前端节点接入。"
    />
  );
}
