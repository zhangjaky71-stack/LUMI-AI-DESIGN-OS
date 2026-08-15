import { describe, expect, it } from "vitest";
import type { AIWorkspaceSnapshot, AgentTaskSummary } from "@/lib/ai-workspace/types";
import { projectAgentTimeline, sanitizeTimelineText } from "./projector";

function snapshot(tasks: readonly AgentTaskSummary[] = []): AIWorkspaceSnapshot {
  return {
    project_id: "project-1",
    project_name: "Project",
    brand_name: "Brand",
    document: {
      document_id: "doc-1",
      version: 7,
      title: "Canvas",
      width: 1080,
      height: 1350,
      selection_options: [],
    },
    references: [],
    run: {
      run_id: "run-1",
      version: 3,
      status: "RUNNING",
      last_event_id: "run-1:4",
      started_at: "2026-08-15T00:00:00.000Z",
      completed_at: null,
      selected_node_ids: [],
      document_version: 7,
      safe_summary: "Preparing campaign direction",
      cost_summary: {
        estimated_microusd: "2500000",
        actual_microusd: "800000",
        credits: "3.2",
        budget_warning: false,
      },
      tasks,
    },
    messages: [],
    artifacts: [],
    approvals: [],
  };
}

describe("Agent Timeline canonical projection", () => {
  it("projects real task counts rather than inventing percentages", () => {
    const view = projectAgentTimeline(snapshot([
      {
        task_id: "visual",
        label: "生成视觉方向",
        status: "RUNNING",
        retryable: true,
        category: "GENERATION",
        safe_summary: "正在生成 4 个可评审方向。",
        completed_units: 2,
        total_units: 4,
      },
    ]));
    const task = view.items.find((item) => item.task_id === "visual");
    expect(task?.progress).toEqual({ completed: 2, total: 4, label: "2/4" });
    expect(JSON.stringify(task)).not.toContain("50%");
  });

  it("keeps only safe tool summaries and never projects unknown debug fields", () => {
    const unsafe = {
      task_id: "research",
      label: "Researching",
      status: "RUNNING" as const,
      retryable: false,
      tool_summaries: [{ id: "tool-1", label: "Read brand guide" }],
      chain_of_thought: "private reasoning",
      raw_tool_payload: { authorization: "Bearer secret" },
    };
    const view = projectAgentTimeline(snapshot([unsafe as AgentTaskSummary]));
    const encoded = JSON.stringify(view);
    expect(encoded).toContain("Read brand guide");
    expect(encoded).not.toContain("private reasoning");
    expect(encoded).not.toContain("Bearer secret");
    expect(encoded).not.toContain("raw_tool_payload");
  });

  it("redacts text that looks like private execution detail", () => {
    expect(sanitizeTimelineText("system prompt: never expose this")).toBe("内部执行细节已隐藏。");
    expect(sanitizeTimelineText("Checked brand consistency")).toBe("Checked brand consistency");
  });

  it("projects provider fallback, retryable error and request id without a stack", () => {
    const view = projectAgentTimeline(snapshot([
      {
        task_id: "render",
        label: "Generate hero",
        status: "FAILED",
        retryable: true,
        category: "GENERATION",
        error: {
          code: "PROVIDER_TIMEOUT",
          safe_message: "主 Provider 超时，任务可重试。",
          retrying: false,
          request_id: "req-public-42",
          provider_fallback: "Primary → Backup image provider",
        },
      },
    ]));
    const item = view.items.find((candidate) => candidate.task_id === "render");
    expect(item?.category).toBe("ERROR");
    expect(item?.error?.provider_fallback).toContain("Backup");
    expect(item?.error?.request_id).toBe("req-public-42");
    expect(JSON.stringify(item)).not.toContain("stack");
  });

  it("keeps current pending approval sticky and stale approvals non-actionable in the projection", () => {
    const base = snapshot();
    const withApproval: AIWorkspaceSnapshot = {
      ...base,
      approvals: [
        {
          approval_id: "approval-current",
          run_id: "run-1",
          expected_run_version: 3,
          state: "PENDING",
          title: "确认方向",
          description: "继续前需要确认。",
          impact: null,
          estimated_cost_microusd: "1000000",
          artifact_version_ids: [],
          expires_at: null,
        },
        {
          approval_id: "approval-old",
          run_id: "run-old",
          expected_run_version: 1,
          state: "STALE",
          title: "旧审批",
          description: "仅供历史查看。",
          impact: null,
          estimated_cost_microusd: null,
          artifact_version_ids: [],
          expires_at: null,
        },
      ],
    };
    const view = projectAgentTimeline(withApproval);
    expect(view.has_waiting_user).toBe(true);
    expect(view.items.find((item) => item.approval_id === "approval-current")?.sticky).toBe(true);
    expect(view.items.find((item) => item.approval_id === "approval-old")?.sticky).toBe(false);
  });

  it("reconstructs the same timeline from the same canonical snapshot after refresh", () => {
    const canonical = snapshot([
      { task_id: "brief", label: "Brief prepared", status: "SUCCEEDED", retryable: false },
    ]);
    expect(projectAgentTimeline(structuredClone(canonical))).toEqual(projectAgentTimeline(canonical));
  });
});
