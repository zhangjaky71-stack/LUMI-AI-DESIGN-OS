import { api } from "@/lib/api/client";
import {
  type AgentRunResource,
  type CanvasSelectionContext,
  type RunControlSnapshot,
  parseAgentRunResource,
  parseRunControlSnapshot,
  selectionClientContext,
} from "@/lib/workspace/types";

export type CreateAgentRunInput = {
  goal: string;
  selection?: CanvasSelectionContext | null;
  budget?: { amount: string; currency: string } | null;
};

export async function createAgentRun(
  organizationId: string,
  projectId: string,
  input: CreateAgentRunInput,
  operationId: string,
): Promise<AgentRunResource> {
  const goal = input.goal.trim();
  if (!goal) throw new Error("AGENT_GOAL_REQUIRED");
  const payload = await api.post<unknown>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/agent-runs`,
    {
      goal,
      ...(input.budget ? { budget: input.budget } : {}),
      client_context: selectionClientContext(input.selection ?? null),
    },
    {
      headers: tenantHeaders(organizationId, { "Idempotency-Key": operationId }),
    },
  );
  return parseAgentRunResource(payload);
}

export async function getAgentRun(
  organizationId: string,
  agentRunId: string,
): Promise<AgentRunResource> {
  const payload = await api.get<unknown>(
    `/api/v1/agent-runs/${encodeURIComponent(agentRunId)}`,
    { headers: tenantHeaders(organizationId) },
  );
  return parseAgentRunResource(payload);
}

export async function getRunControl(
  organizationId: string,
  agentRunId: string,
): Promise<RunControlSnapshot> {
  const payload = await api.get<unknown>(
    `/api/v1/agent-runs/${encodeURIComponent(agentRunId)}/control`,
    { headers: tenantHeaders(organizationId) },
  );
  return parseRunControlSnapshot(payload);
}

export async function cancelAgentRun(
  organizationId: string,
  agentRunId: string,
  operationId: string,
): Promise<void> {
  await api.post<unknown>(
    `/api/v1/agent-runs/${encodeURIComponent(agentRunId)}/cancel`,
    undefined,
    {
      headers: tenantHeaders(organizationId, { "Idempotency-Key": operationId }),
    },
  );
}

export async function resumeAgentRun(
  organizationId: string,
  agentRunId: string,
  input: {
    operationId: string;
    resumeVersion: number;
    interruptId: string;
    kind: "approval" | "external_job" | "input";
    value: unknown;
  },
): Promise<RunControlSnapshot> {
  await api.post<unknown>(
    `/api/v1/agent-runs/${encodeURIComponent(agentRunId)}/resume`,
    {
      operation_id: input.operationId,
      resume_version: input.resumeVersion,
      interrupt_id: input.interruptId,
      kind: input.kind,
      value: input.value,
    },
    { headers: tenantHeaders(organizationId) },
  );
  return getRunControl(organizationId, agentRunId);
}

export function tenantHeaders(
  organizationId: string,
  extra: Record<string, string> = {},
): Record<string, string> {
  if (!organizationId.trim()) throw new Error("ORGANIZATION_ID_REQUIRED");
  return { "X-Organization-ID": organizationId, ...extra };
}
