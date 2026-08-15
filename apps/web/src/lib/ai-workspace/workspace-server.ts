import type {
  AIWorkspaceBootstrap,
  AIWorkspaceSnapshot,
  DeterministicWorkspaceSeed,
  WorkspaceApproval,
  WorkspaceMessage,
} from "./types";

function message(
  id: string,
  kind: WorkspaceMessage["kind"],
  text: string,
  options: Partial<Pick<WorkspaceMessage, "run_id" | "artifact_version_id" | "approval_id" | "warning_code">> = {},
): WorkspaceMessage {
  return {
    id,
    kind,
    created_at: "2026-08-15T01:40:00.000Z",
    text,
    run_id: options.run_id ?? null,
    artifact_version_id: options.artifact_version_id ?? null,
    approval_id: options.approval_id ?? null,
    warning_code: options.warning_code ?? null,
  };
}

function seed(projectId: string): DeterministicWorkspaceSeed {
  const staleApproval: WorkspaceApproval = {
    approval_id: "approval-stale-demo",
    run_id: "run-previous",
    expected_run_version: 1,
    state: "STALE",
    title: "旧方向确认",
    description: "该审批来自已结束的旧 Run，仅用于验证 stale 防护。",
    impact: null,
    estimated_cost_microusd: null,
    artifact_version_ids: [],
    expires_at: "2026-08-14T00:00:00.000Z",
  };
  const snapshot: AIWorkspaceSnapshot = {
    project_id: projectId,
    project_name: projectId === "project-summer-launch" ? "夏季新品发布" : "AI Design Project",
    brand_name: projectId === "project-summer-launch" ? "LUMI Coffee" : null,
    document: {
      document_id: `document:${projectId}`,
      version: 7,
      title: "Campaign Canvas",
      width: 1440,
      height: 1800,
      selection_options: [
        { node_id: "node-hero-product", label: "Hero Product", kind: "image", locked_identity: true },
        { node_id: "node-headline", label: "Headline", kind: "text", locked_identity: false },
        { node_id: "node-offer", label: "Offer Badge", kind: "shape", locked_identity: false },
      ],
    },
    references: [
      {
        id: "reference:asset-lumi-product",
        asset_id: "asset-lumi-product",
        file_name: "hero-product.png",
        mime_type: "image/png",
        size_bytes: 482_000,
        role: "product",
        scan_status: "READY",
        failure_code: null,
      },
      {
        id: "reference:asset-lumi-guide",
        asset_id: "asset-lumi-guide",
        file_name: "brand-guide.pdf",
        mime_type: "application/pdf",
        size_bytes: 1_240_000,
        role: "brand_guide",
        scan_status: "READY",
        failure_code: null,
      },
    ],
    run: null,
    messages: [
      message("message-welcome", "ANSWER", "项目工作区已就绪。你可以直接描述要完成的设计任务。"),
      message(
        "message-provider-warning",
        "WARNING",
        "主图像 Provider 当前处于降级状态；如触发生成，将在策略允许时使用备用 Provider。",
        { warning_code: "PROVIDER_FALLBACK" },
      ),
      message("message-stale-approval", "APPROVAL", staleApproval.description, {
        run_id: staleApproval.run_id,
        approval_id: staleApproval.approval_id,
      }),
    ],
    artifacts: [],
    approvals: [staleApproval],
  };
  return { snapshot, stale_approval_id: staleApproval.approval_id };
}

export function getAIWorkspaceBootstrap(projectId: string): AIWorkspaceBootstrap {
  const e2e =
    process.env.NODE_ENV !== "production" && process.env.LUMI_AI_WORKSPACE_E2E === "1";
  return e2e ? { mode: "e2e", seed: seed(projectId) } : { mode: "http", seed: null };
}
