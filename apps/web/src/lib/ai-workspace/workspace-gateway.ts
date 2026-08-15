import { LumiApiClient } from "@/lib/app-shell/api-client";
import {
  decodeSseFrame,
  validateApprovalDecision,
  validateStartRunInput,
  workspaceProblem,
} from "./contracts";
import type {
  AIWorkspaceBootstrap,
  AIWorkspaceSnapshot,
  AgentRunSnapshot,
  ApprovalDecisionInput,
  DeterministicWorkspaceSeed,
  PlaceArtifactInput,
  RetryTaskInput,
  RunControlInput,
  StartRunInput,
  WorkspaceApproval,
  WorkspaceArtifact,
  WorkspaceEvent,
  WorkspaceMessage,
} from "./types";

export interface WorkspaceStreamOptions {
  readonly last_event_id: string | null;
  readonly signal: AbortSignal;
  readonly on_event: (event: WorkspaceEvent) => void;
}

export interface AIWorkspaceGateway {
  getWorkspace(organizationId: string, projectId: string, signal?: AbortSignal): Promise<AIWorkspaceSnapshot>;
  startRun(organizationId: string, input: StartRunInput, signal?: AbortSignal): Promise<AIWorkspaceSnapshot>;
  pauseRun(organizationId: string, input: RunControlInput, signal?: AbortSignal): Promise<AgentRunSnapshot>;
  resumeRun(organizationId: string, input: RunControlInput, signal?: AbortSignal): Promise<AgentRunSnapshot>;
  stopRun(organizationId: string, input: RunControlInput, signal?: AbortSignal): Promise<AgentRunSnapshot>;
  retryTask(organizationId: string, input: RetryTaskInput, signal?: AbortSignal): Promise<AgentRunSnapshot>;
  decideApproval(organizationId: string, input: ApprovalDecisionInput, signal?: AbortSignal): Promise<AIWorkspaceSnapshot>;
  placeArtifact(organizationId: string, input: PlaceArtifactInput, signal?: AbortSignal): Promise<AIWorkspaceSnapshot>;
  streamRun(organizationId: string, projectId: string, runId: string, options: WorkspaceStreamOptions): Promise<void>;
}

function requestOptions(signal?: AbortSignal): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

export class HttpAIWorkspaceGateway implements AIWorkspaceGateway {
  readonly #api: LumiApiClient;
  readonly #transport: typeof fetch;

  constructor(api: LumiApiClient, transport: typeof fetch = globalThis.fetch.bind(globalThis)) {
    this.#api = api;
    this.#transport = transport;
  }

  getWorkspace(_organizationId: string, projectId: string, signal?: AbortSignal) {
    return this.#api.get<AIWorkspaceSnapshot>(
      `/projects/${encodeURIComponent(projectId)}/ai-workspace`,
      requestOptions(signal),
    );
  }

  startRun(_organizationId: string, input: StartRunInput, signal?: AbortSignal) {
    const safe = validateStartRunInput(input);
    return this.#api.post<AIWorkspaceSnapshot, StartRunInput>(
      `/projects/${encodeURIComponent(safe.project_id)}/agent-runs`,
      safe,
      { idempotency_key: crypto.randomUUID(), ...requestOptions(signal) },
    );
  }

  pauseRun(_organizationId: string, input: RunControlInput, signal?: AbortSignal) {
    return this.#control(input, "pause", signal);
  }

  resumeRun(_organizationId: string, input: RunControlInput, signal?: AbortSignal) {
    return this.#control(input, "resume", signal);
  }

  stopRun(_organizationId: string, input: RunControlInput, signal?: AbortSignal) {
    return this.#control(input, "cancel", signal);
  }

  retryTask(_organizationId: string, input: RetryTaskInput, signal?: AbortSignal) {
    return this.#api.post<AgentRunSnapshot, { expected_run_version: number }>(
      `/agent-runs/${encodeURIComponent(input.run_id)}/tasks/${encodeURIComponent(input.task_id)}/retry`,
      { expected_run_version: input.expected_run_version },
      { idempotency_key: crypto.randomUUID(), ...requestOptions(signal) },
    );
  }

  decideApproval(_organizationId: string, input: ApprovalDecisionInput, signal?: AbortSignal) {
    return this.#api.post<AIWorkspaceSnapshot, ApprovalDecisionInput>(
      `/approvals/${encodeURIComponent(input.approval_id)}/decisions`,
      input,
      { idempotency_key: crypto.randomUUID(), ...requestOptions(signal) },
    );
  }

  placeArtifact(_organizationId: string, input: PlaceArtifactInput, signal?: AbortSignal) {
    return this.#api.post<AIWorkspaceSnapshot, PlaceArtifactInput>(
      `/canvas/documents/${encodeURIComponent(input.document_id)}/artifact-placements`,
      input,
      { idempotency_key: crypto.randomUUID(), ...requestOptions(signal) },
    );
  }

  async streamRun(
    organizationId: string,
    projectId: string,
    runId: string,
    options: WorkspaceStreamOptions,
  ): Promise<void> {
    const headers = new Headers({
      accept: "text/event-stream",
      "cache-control": "no-cache",
      "x-lumi-organization-id": organizationId,
    });
    if (options.last_event_id) headers.set("last-event-id", options.last_event_id);
    const response = await this.#transport(
      `/api/v1/projects/${encodeURIComponent(projectId)}/agent-runs/${encodeURIComponent(runId)}/events`,
      {
        method: "GET",
        credentials: "same-origin",
        headers,
        signal: options.signal,
      },
    );
    if (!response.ok) throw workspaceProblem("STREAM_UNAVAILABLE", response.status);
    if (!response.body) throw workspaceProblem("STREAM_BODY_MISSING", 502);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done }).replaceAll("\r\n", "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = decodeSseFrame(frame);
        if (event) options.on_event(event);
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }
    if (buffer.trim()) {
      const event = decodeSseFrame(buffer.trim());
      if (event) options.on_event(event);
    }
  }

  #control(input: RunControlInput, action: "pause" | "resume" | "cancel", signal?: AbortSignal) {
    return this.#api.post<AgentRunSnapshot, { expected_run_version: number }>(
      `/agent-runs/${encodeURIComponent(input.run_id)}/${action}`,
      { expected_run_version: input.expected_run_version },
      { idempotency_key: crypto.randomUUID(), ...requestOptions(signal) },
    );
  }
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function at(sequence: number): string {
  return new Date(Date.UTC(2026, 7, 15, 2, 10, sequence)).toISOString();
}

function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

export class DeterministicAIWorkspaceGateway implements AIWorkspaceGateway {
  #snapshot: AIWorkspaceSnapshot;
  readonly #staleApprovalId: string;
  #counter = 20;

  constructor(seed: DeterministicWorkspaceSeed) {
    this.#snapshot = clone(seed.snapshot);
    this.#staleApprovalId = seed.stale_approval_id;
  }

  async getWorkspace(organizationId: string, projectId: string, signal?: AbortSignal) {
    this.#assertScope(organizationId, projectId, signal);
    return clone(this.#snapshot);
  }

  async startRun(organizationId: string, input: StartRunInput, signal?: AbortSignal) {
    this.#assertScope(organizationId, input.project_id, signal);
    const safe = validateStartRunInput(input);
    const runId = `run-e2e-${++this.#counter}`;
    const run: AgentRunSnapshot = {
      run_id: runId,
      version: 1,
      status: "RUNNING",
      last_event_id: null,
      started_at: at(this.#counter),
      completed_at: null,
      selected_node_ids: safe.selected_node_ids,
      document_version: safe.document_version,
      tasks: [
        { task_id: `${runId}:brief`, label: "理解 Brief", status: "RUNNING", retryable: false },
        { task_id: `${runId}:visual`, label: "生成视觉方向", status: "PENDING", retryable: true },
      ],
    };
    const user: WorkspaceMessage = {
      id: `message-user-${this.#counter}`,
      kind: "USER",
      created_at: at(this.#counter),
      text: safe.prompt,
      run_id: runId,
      artifact_version_id: null,
      approval_id: null,
      warning_code: null,
    };
    this.#snapshot = { ...this.#snapshot, run, messages: [...this.#snapshot.messages, user] };
    return clone(this.#snapshot);
  }

  async pauseRun(organizationId: string, input: RunControlInput, signal?: AbortSignal) {
    const run = this.#requireRun(organizationId, input, signal);
    if (run.status !== "RUNNING") throw workspaceProblem("RUN_NOT_PAUSABLE");
    return this.#replaceRun({ ...run, version: run.version + 1, status: "PAUSED" });
  }

  async resumeRun(organizationId: string, input: RunControlInput, signal?: AbortSignal) {
    const run = this.#requireRun(organizationId, input, signal);
    if (run.status !== "PAUSED") throw workspaceProblem("RUN_NOT_RESUMABLE");
    return this.#replaceRun({ ...run, version: run.version + 1, status: "RUNNING" });
  }

  async stopRun(organizationId: string, input: RunControlInput, signal?: AbortSignal) {
    const run = this.#requireRun(organizationId, input, signal);
    if (!["RUNNING", "PAUSED", "QUEUED"].includes(run.status)) throw workspaceProblem("RUN_NOT_CANCELABLE");
    return this.#replaceRun({
      ...run,
      version: run.version + 1,
      status: "CANCELED",
      completed_at: at(++this.#counter),
      tasks: run.tasks.map((task) =>
        task.status === "RUNNING" || task.status === "PENDING"
          ? { ...task, status: "CANCELED" as const }
          : task,
      ),
    });
  }

  async retryTask(organizationId: string, input: RetryTaskInput, signal?: AbortSignal) {
    const run = this.#requireRun(organizationId, input, signal);
    const target = run.tasks.find((task) => task.task_id === input.task_id);
    if (!target || target.status !== "FAILED" || !target.retryable) throw workspaceProblem("TASK_NOT_RETRYABLE");
    return this.#replaceRun({
      ...run,
      version: run.version + 1,
      status: "RUNNING",
      completed_at: null,
      tasks: run.tasks.map((task) =>
        task.task_id === input.task_id ? { ...task, status: "RUNNING" as const } : task,
      ),
    });
  }

  async decideApproval(organizationId: string, input: ApprovalDecisionInput, signal?: AbortSignal) {
    this.#assertScope(organizationId, this.#snapshot.project_id, signal);
    const approval = this.#snapshot.approvals.find((value) => value.approval_id === input.approval_id);
    if (!approval) throw workspaceProblem("APPROVAL_NOT_FOUND", 404);
    if (input.approval_id === this.#staleApprovalId) throw workspaceProblem("APPROVAL_STALE");
    const safe = validateApprovalDecision(input, approval, this.#snapshot.run);
    const state: WorkspaceApproval["state"] =
      safe.decision === "APPROVE" ? "APPROVED" : safe.decision === "REJECT" ? "REJECTED" : "CHANGES_REQUESTED";
    this.#snapshot = {
      ...this.#snapshot,
      approvals: this.#snapshot.approvals.map((value) =>
        value.approval_id === safe.approval_id ? { ...value, state } : value,
      ),
      messages: [
        ...this.#snapshot.messages,
        {
          id: `message-decision-${++this.#counter}`,
          kind: "STATUS",
          created_at: at(this.#counter),
          text: `审批已记录：${safe.decision}${safe.request_changes_note ? `：${safe.request_changes_note}` : ""}`,
          run_id: safe.run_id,
          artifact_version_id: null,
          approval_id: safe.approval_id,
          warning_code: null,
        },
      ],
    };
    return clone(this.#snapshot);
  }

  async placeArtifact(organizationId: string, input: PlaceArtifactInput, signal?: AbortSignal) {
    this.#assertScope(organizationId, input.project_id, signal);
    if (input.document_id !== this.#snapshot.document.document_id) throw workspaceProblem("DOCUMENT_NOT_FOUND", 404);
    if (input.expected_document_version !== this.#snapshot.document.version) throw workspaceProblem("DOCUMENT_VERSION_CONFLICT");
    const artifact = this.#snapshot.artifacts.find(
      (value) => value.artifact_id === input.artifact_id && value.version_id === input.artifact_version_id,
    );
    if (!artifact) throw workspaceProblem("ARTIFACT_VERSION_NOT_FOUND", 404);
    this.#snapshot = {
      ...this.#snapshot,
      document: { ...this.#snapshot.document, version: this.#snapshot.document.version + 1 },
      messages: [
        ...this.#snapshot.messages,
        {
          id: `message-place-${++this.#counter}`,
          kind: "STATUS",
          created_at: at(this.#counter),
          text: `已将 ${artifact.title} v${artifact.version} 放到 Canvas。`,
          run_id: this.#snapshot.run?.run_id ?? null,
          artifact_version_id: artifact.version_id,
          approval_id: null,
          warning_code: null,
        },
      ],
    };
    return clone(this.#snapshot);
  }

  async streamRun(
    organizationId: string,
    projectId: string,
    runId: string,
    options: WorkspaceStreamOptions,
  ): Promise<void> {
    this.#assertScope(organizationId, projectId, options.signal);
    const run = this.#snapshot.run;
    if (!run || run.run_id !== runId) throw workspaceProblem("RUN_NOT_FOUND", 404);

    const artifact: WorkspaceArtifact = {
      artifact_id: `artifact-${runId}`,
      version_id: `artifact-version-${runId}-1`,
      version: 1,
      title: "夏季新品主视觉方向 A",
      media_type: "image/png",
      preview_label: "4:5 · Product hero",
      created_at: at(31),
    };
    const approval: WorkspaceApproval = {
      approval_id: `approval-${runId}`,
      run_id: runId,
      expected_run_version: run.version,
      state: "PENDING",
      title: "确认主视觉方向",
      description: "方向 A 已生成。确认后才会继续扩展门店海报与社媒尺寸。",
      impact: "继续将基于当前构图扩展 3 个交付物。",
      estimated_cost_microusd: "1800000",
      artifact_version_ids: [artifact.version_id],
      expires_at: "2026-08-16T00:00:00.000Z",
    };
    const status = (id: string, text: string, sequence: number): WorkspaceMessage => ({
      id,
      kind: "STATUS",
      created_at: at(sequence),
      text,
      run_id: runId,
      artifact_version_id: null,
      approval_id: null,
      warning_code: null,
    });
    const events: WorkspaceEvent[] = [
      {
        id: `${runId}:1`, sequence: 1, run_id: runId, type: "message.created",
        message: status(`${runId}:message:1`, "正在分析 Brief、Brand Kit 与选中对象。", 28),
      },
      {
        id: `${runId}:2`, sequence: 2, run_id: runId, type: "message.created",
        message: status(`${runId}:message:2`, "已锁定产品身份约束，正在生成视觉方向。", 29),
      },
      {
        id: `${runId}:3`, sequence: 3, run_id: runId, type: "artifact.created", artifact,
        message: { ...status(`${runId}:message:3`, "已生成可评审的主视觉 Artifact v1。", 31), kind: "ARTIFACT", artifact_version_id: artifact.version_id },
      },
      {
        id: `${runId}:4`, sequence: 4, run_id: runId, type: "approval.required", approval,
        message: { ...status(`${runId}:message:4`, approval.description, 32), kind: "APPROVAL", approval_id: approval.approval_id },
      },
      {
        id: `${runId}:5`, sequence: 5, run_id: runId, type: "run.status",
        run: { ...run, status: "PAUSED", last_event_id: `${runId}:5` },
      },
    ];
    const lastSequence = options.last_event_id
      ? Number(options.last_event_id.split(":").at(-1) ?? "0")
      : 0;
    for (const event of events) {
      if (event.sequence <= lastSequence) continue;
      await delay(120, options.signal);
      if (this.#snapshot.run?.status === "CANCELED") return;
      this.#applyCanonicalEvent(event);
      options.on_event(clone(event));
      if (event.sequence === 2) options.on_event(clone(event));
    }
  }

  #applyCanonicalEvent(event: WorkspaceEvent): void {
    if (event.type === "run.status") {
      this.#snapshot = { ...this.#snapshot, run: event.run };
    } else if (event.type === "message.created") {
      if (!this.#snapshot.messages.some((value) => value.id === event.message.id)) {
        this.#snapshot = { ...this.#snapshot, messages: [...this.#snapshot.messages, event.message] };
      }
    } else if (event.type === "artifact.created") {
      this.#snapshot = {
        ...this.#snapshot,
        artifacts: this.#snapshot.artifacts.some((value) => value.version_id === event.artifact.version_id)
          ? this.#snapshot.artifacts : [...this.#snapshot.artifacts, event.artifact],
        messages: this.#snapshot.messages.some((value) => value.id === event.message.id)
          ? this.#snapshot.messages : [...this.#snapshot.messages, event.message],
      };
    } else {
      this.#snapshot = {
        ...this.#snapshot,
        approvals: this.#snapshot.approvals.some((value) => value.approval_id === event.approval.approval_id)
          ? this.#snapshot.approvals : [...this.#snapshot.approvals, event.approval],
        messages: this.#snapshot.messages.some((value) => value.id === event.message.id)
          ? this.#snapshot.messages : [...this.#snapshot.messages, event.message],
      };
    }
    if (this.#snapshot.run?.run_id === event.run_id) {
      this.#snapshot = { ...this.#snapshot, run: { ...this.#snapshot.run, last_event_id: event.id } };
    }
  }

  #replaceRun(run: AgentRunSnapshot): AgentRunSnapshot {
    this.#snapshot = { ...this.#snapshot, run };
    return clone(run);
  }

  #requireRun(organizationId: string, input: RunControlInput, signal?: AbortSignal): AgentRunSnapshot {
    this.#assertScope(organizationId, this.#snapshot.project_id, signal);
    const run = this.#snapshot.run;
    if (!run || run.run_id !== input.run_id) throw workspaceProblem("RUN_NOT_FOUND", 404);
    if (run.version !== input.expected_run_version) throw workspaceProblem("RUN_VERSION_CONFLICT");
    return run;
  }

  #assertScope(organizationId: string, projectId: string, signal?: AbortSignal): void {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (organizationId !== "org-lumi" && organizationId !== "org-northstar") {
      throw workspaceProblem("ORGANIZATION_FORBIDDEN", 403);
    }
    if (projectId !== this.#snapshot.project_id) throw workspaceProblem("PROJECT_NOT_FOUND", 404);
  }
}

export function getAIWorkspaceGateway(api: LumiApiClient, bootstrap: AIWorkspaceBootstrap): AIWorkspaceGateway {
  if (bootstrap.mode !== "e2e") return new HttpAIWorkspaceGateway(api);
  if (!bootstrap.seed) throw new Error("AI_WORKSPACE_E2E_SEED_REQUIRED");
  return new DeterministicAIWorkspaceGateway(bootstrap.seed);
}
