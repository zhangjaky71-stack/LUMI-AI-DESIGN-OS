import type {
  AIWorkspaceBootstrap,
  AIWorkspaceSnapshot,
  AgentRunSnapshot,
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

function seededRun(projectId: string): AgentRunSnapshot | null {
  if (projectId === "project-agent-retry") {
    return {
      run_id: "run-retry-seed",
      version: 4,
      status: "FAILED",
      last_event_id: "run-retry-seed:12",
      started_at: "2026-08-15T01:31:00.000Z",
      completed_at: "2026-08-15T01:34:00.000Z",
      selected_node_ids: [],
      document_version: 7,
      safe_summary: "视觉方向生成在 Provider timeout 后停止，等待用户重试。",
      cost_summary: {
        estimated_microusd: "2600000",
        actual_microusd: "940000",
        credits: "3.8",
        budget_warning: false,
      },
      tasks: [
        {
          task_id: "run-retry-seed:brief",
          label: "理解 Brief",
          status: "SUCCEEDED",
          retryable: false,
          category: "AGENT",
          safe_summary: "Brief、Brand Kit 与参考素材已整理。",
          started_at: "2026-08-15T01:31:00.000Z",
          finished_at: "2026-08-15T01:31:24.000Z",
          tool_summaries: [{ id: "tool-brand", label: "Read brand guide" }],
        },
        {
          task_id: "run-retry-seed:visual",
          label: "生成视觉方向",
          status: "FAILED",
          retryable: true,
          category: "GENERATION",
          safe_summary: "已完成 2/4 个候选方向后主 Provider 超时。",
          started_at: "2026-08-15T01:31:25.000Z",
          finished_at: "2026-08-15T01:34:00.000Z",
          completed_units: 2,
          total_units: 4,
          tool_summaries: [{ id: "tool-identity", label: "Checked product identity constraints" }],
          error: {
            code: "PROVIDER_TIMEOUT",
            safe_message: "主图像 Provider 超时；已保留可重试任务状态。",
            retrying: false,
            request_id: "req-timeline-retry-01",
            provider_fallback: "Primary image provider → Backup provider available on retry",
          },
        },
      ],
    };
  }

  if (projectId === "project-agent-cancelled") {
    return {
      run_id: "run-cancelled-seed",
      version: 3,
      status: "CANCELED",
      last_event_id: "run-cancelled-seed:8",
      started_at: "2026-08-15T01:20:00.000Z",
      completed_at: "2026-08-15T01:22:00.000Z",
      selected_node_ids: [],
      document_version: 7,
      safe_summary: "Run 已由用户停止，未继续执行剩余生成步骤。",
      tasks: [
        {
          task_id: "run-cancelled-seed:brief",
          label: "理解 Brief",
          status: "SUCCEEDED",
          retryable: false,
          category: "AGENT",
          safe_summary: "Brief 已准备完成。",
        },
        {
          task_id: "run-cancelled-seed:visual",
          label: "生成视觉方向",
          status: "CANCELED",
          retryable: true,
          category: "GENERATION",
          safe_summary: "任务在用户停止 Run 后取消。",
          completed_units: 1,
          total_units: 4,
        },
      ],
    };
  }

  return null;
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
  const run = seededRun(projectId);
  const snapshot: AIWorkspaceSnapshot = {
    project_id: projectId,
    project_name:
      projectId === "project-summer-launch"
        ? "夏季新品发布"
        : projectId === "project-agent-retry"
          ? "Agent Retry Timeline"
          : projectId === "project-agent-cancelled"
            ? "Cancelled Run Timeline"
            : "AI Design Project",
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
    run,
    messages: [
      message("message-welcome", "ANSWER", "项目工作区已就绪。你可以直接描述要完成的设计任务。"),
      message(
        "message-provider-warning",
        "WARNING",
        "主图像 Provider 当前处于降级状态；如触发生成，将在策略允许时使用备用 Provider。",
        { warning_code: "PROVIDER_FALLBACK" },
      ),
      ...(run?.status === "FAILED"
        ? [message("message-retry-error", "ERROR", "视觉方向生成失败；可以从失败任务安全重试。", {
            run_id: run.run_id,
            warning_code: "PROVIDER_TIMEOUT",
          })]
        : []),
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
