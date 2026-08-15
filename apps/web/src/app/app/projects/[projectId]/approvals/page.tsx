import { ApprovalCenter } from "@/components/approval-ui/approval-center";
import { getApprovalBootstrap } from "@/lib/approval-ui/approval-server";

export const dynamic = "force-dynamic";

export default async function ApprovalsPage({ params }: Readonly<{ params: Promise<{ projectId: string }> }>) {
  const { projectId } = await params;
  return <ApprovalCenter projectId={projectId} bootstrap={getApprovalBootstrap(projectId)} />;
}
