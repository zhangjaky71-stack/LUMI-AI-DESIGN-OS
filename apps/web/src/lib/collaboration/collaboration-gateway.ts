import { LumiApiClient } from "@/lib/app-shell/api-client";
import { assertExactCollaborationVersion, validateCommentBody } from "./contracts";
import type {
  CollaborationBootstrap,
  CollaborationOperationInput,
  CollaborationOperationResult,
  CollaborationPresence,
  CollaborationRealtimeEvent,
  CollaborationThread,
  CollaborationWorkspaceSnapshot,
  CreateCollaborationThreadInput,
  ReplyCollaborationThreadInput,
} from "./types";

export interface CollaborationRealtimeConnection {
  close(): void;
}

export interface CollaborationGateway {
  loadWorkspace(projectId: string, signal?: AbortSignal): Promise<CollaborationWorkspaceSnapshot>;
  createThread(projectId: string, input: CreateCollaborationThreadInput, signal?: AbortSignal): Promise<CollaborationThread>;
  reply(projectId: string, threadId: string, input: ReplyCollaborationThreadInput, signal?: AbortSignal): Promise<CollaborationThread>;
  setThreadStatus(projectId: string, threadId: string, status: "RESOLVED" | "REOPENED", signal?: AbortSignal): Promise<CollaborationThread>;
  submitOperations(projectId: string, documentId: string, input: CollaborationOperationInput, signal?: AbortSignal): Promise<CollaborationOperationResult>;
  reconnect(projectId: string, documentId: string, input: CollaborationOperationInput, signal?: AbortSignal): Promise<CollaborationOperationResult>;
  openRealtime(projectId: string, documentId: string, listener: (event: CollaborationRealtimeEvent) => void): CollaborationRealtimeConnection;
}

function request(signal?: AbortSignal): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

export class HttpCollaborationGateway implements CollaborationGateway {
  readonly #api: LumiApiClient;

  constructor(api = new LumiApiClient()) {
    this.#api = api;
  }

  loadWorkspace(projectId: string, signal?: AbortSignal): Promise<CollaborationWorkspaceSnapshot> {
    return this.#api.get<CollaborationWorkspaceSnapshot>(
      `/projects/${encodeURIComponent(projectId)}/collaboration`,
      request(signal),
    );
  }

  createThread(projectId: string, input: CreateCollaborationThreadInput, signal?: AbortSignal): Promise<CollaborationThread> {
    validateCommentBody(input.body);
    assertExactCollaborationVersion(input.anchor.artifact_version_id, "artifact_version");
    assertExactCollaborationVersion(input.anchor.design_document_version_id, "design_version");
    return this.#api.post<CollaborationThread, CreateCollaborationThreadInput>(
      `/projects/${encodeURIComponent(projectId)}/collaboration/threads`,
      input,
      { idempotency_key: crypto.randomUUID(), ...request(signal) },
    );
  }

  reply(projectId: string, threadId: string, input: ReplyCollaborationThreadInput, signal?: AbortSignal): Promise<CollaborationThread> {
    validateCommentBody(input.body);
    return this.#api.post<CollaborationThread, ReplyCollaborationThreadInput>(
      `/projects/${encodeURIComponent(projectId)}/collaboration/threads/${encodeURIComponent(threadId)}/replies`,
      input,
      { idempotency_key: crypto.randomUUID(), ...request(signal) },
    );
  }

  setThreadStatus(projectId: string, threadId: string, status: "RESOLVED" | "REOPENED", signal?: AbortSignal): Promise<CollaborationThread> {
    const action = status === "RESOLVED" ? "resolve" : "reopen";
    return this.#api.post<CollaborationThread, Record<string, never>>(
      `/projects/${encodeURIComponent(projectId)}/collaboration/threads/${encodeURIComponent(threadId)}:${action}`,
      {},
      { idempotency_key: crypto.randomUUID(), ...request(signal) },
    );
  }

  submitOperations(projectId: string, documentId: string, input: CollaborationOperationInput, signal?: AbortSignal): Promise<CollaborationOperationResult> {
    assertExactCollaborationVersion(input.base_version_id, "base_design_version");
    return this.#api.post<CollaborationOperationResult, CollaborationOperationInput>(
      `/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}/collaboration/operations`,
      input,
      { idempotency_key: crypto.randomUUID(), ...request(signal) },
    );
  }

  reconnect(projectId: string, documentId: string, input: CollaborationOperationInput, signal?: AbortSignal): Promise<CollaborationOperationResult> {
    assertExactCollaborationVersion(input.base_version_id, "base_design_version");
    return this.#api.post<CollaborationOperationResult, CollaborationOperationInput>(
      `/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}/collaboration/reconnect`,
      input,
      { idempotency_key: crypto.randomUUID(), ...request(signal) },
    );
  }

  openRealtime(projectId: string, documentId: string, listener: (event: CollaborationRealtimeEvent) => void): CollaborationRealtimeConnection {
    if (typeof window === "undefined") return { close() {} };
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = new URL(
      `/api/v1/projects/${encodeURIComponent(projectId)}/collaboration/ws`,
      `${scheme}//${window.location.host}`,
    );
    url.searchParams.set("document_id", documentId);
    const socket = new WebSocket(url);
    socket.addEventListener("open", () => listener({ type: "CONNECTED" }));
    socket.addEventListener("close", () => listener({ type: "OFFLINE" }));
    socket.addEventListener("error", () => listener({ type: "RECONNECTING" }));
    socket.addEventListener("message", (message) => {
      const event = parseRealtimeEvent(message.data);
      if (event) listener(event);
    });
    return { close: () => socket.close(1000, "page closed") };
  }
}

function parseRealtimeEvent(raw: unknown): CollaborationRealtimeEvent | null {
  if (typeof raw !== "string") return null;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  if (item.type === "PRESENCE_SNAPSHOT" && Array.isArray(item.presence)) {
    return { type: "PRESENCE_SNAPSHOT", presence: item.presence as readonly CollaborationPresence[] };
  }
  if (item.type === "AWARENESS_UPDATE" && item.presence && typeof item.presence === "object") {
    return { type: "AWARENESS_UPDATE", presence: item.presence as CollaborationPresence };
  }
  if (item.type === "WRITE_REJECTED" && typeof item.code === "string") {
    return { type: "WRITE_REJECTED", code: item.code };
  }
  return null;
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function nextVersion(value: string): string {
  const match = value.match(/^(.*v)(\d+)$/);
  return match ? `${match[1]}${Number(match[2]) + 1}` : `${value}-collab`;
}

export class DeterministicCollaborationGateway implements CollaborationGateway {
  #workspace: CollaborationWorkspaceSnapshot;
  #counter = 610;

  constructor(workspace: CollaborationWorkspaceSnapshot) {
    this.#workspace = clone(workspace);
  }

  async loadWorkspace(projectId: string, signal?: AbortSignal): Promise<CollaborationWorkspaceSnapshot> {
    this.#assert(projectId, this.#workspace.document_id, signal);
    return clone(this.#workspace);
  }

  async createThread(projectId: string, input: CreateCollaborationThreadInput, signal?: AbortSignal): Promise<CollaborationThread> {
    this.#assert(projectId, this.#workspace.document_id, signal);
    const current = this.#workspace.current_user;
    const thread: CollaborationThread = {
      thread_id: `collaboration-thread-${++this.#counter}`,
      anchor: {
        project_id: projectId,
        ...input.anchor,
        historical: input.anchor.design_document_version_id !== this.#workspace.canonical_version_id,
      },
      status: "OPEN",
      messages: [{
        comment_id: `collaboration-comment-${this.#counter}`,
        actor: current,
        body: validateCommentBody(input.body),
        mention_actor_ids: [...input.mention_actor_ids],
        created_at: "2026-08-15T06:31:00.000Z",
        edited_at: null,
        deleted_at: null,
      }],
      created_at: "2026-08-15T06:31:00.000Z",
    };
    this.#workspace = { ...this.#workspace, threads: [thread, ...this.#workspace.threads] };
    return clone(thread);
  }

  async reply(projectId: string, threadId: string, input: ReplyCollaborationThreadInput, signal?: AbortSignal): Promise<CollaborationThread> {
    this.#assert(projectId, this.#workspace.document_id, signal);
    const thread = this.#thread(threadId);
    const updated: CollaborationThread = {
      ...thread,
      messages: [...thread.messages, {
        comment_id: `collaboration-comment-${++this.#counter}`,
        actor: this.#workspace.current_user,
        body: validateCommentBody(input.body),
        mention_actor_ids: [...input.mention_actor_ids],
        created_at: "2026-08-15T06:32:00.000Z",
        edited_at: null,
        deleted_at: null,
      }],
    };
    this.#replaceThread(updated);
    return clone(updated);
  }

  async setThreadStatus(projectId: string, threadId: string, status: "RESOLVED" | "REOPENED", signal?: AbortSignal): Promise<CollaborationThread> {
    this.#assert(projectId, this.#workspace.document_id, signal);
    const updated: CollaborationThread = { ...this.#thread(threadId), status };
    this.#replaceThread(updated);
    return clone(updated);
  }

  async submitOperations(projectId: string, documentId: string, input: CollaborationOperationInput, signal?: AbortSignal): Promise<CollaborationOperationResult> {
    this.#assert(projectId, documentId, signal);
    const before = this.#workspace.canonical_version_id;
    const after = nextVersion(before);
    this.#workspace = { ...this.#workspace, canonical_version_id: after };
    return clone({
      base_version_id: input.base_version_id,
      canonical_version_before: before,
      canonical_version_after: after,
      accepted_operation_ids: input.operations.map((item) => item.operation_id),
      conflicts: [],
      rebased: input.base_version_id !== before,
    });
  }

  async reconnect(projectId: string, documentId: string, input: CollaborationOperationInput, signal?: AbortSignal): Promise<CollaborationOperationResult> {
    this.#assert(projectId, documentId, signal);
    const local = input.operations[0];
    if (!local) throw new Error("COLLABORATION_OPERATIONS_REQUIRED");
    const remoteVersion = nextVersion(input.base_version_id);
    this.#workspace = { ...this.#workspace, canonical_version_id: remoteVersion };
    return clone({
      base_version_id: input.base_version_id,
      canonical_version_before: remoteVersion,
      canonical_version_after: remoteVersion,
      accepted_operation_ids: [],
      conflicts: [{
        local_operation: local,
        remote_operation_id: "collaboration-e2e-remote-op",
        remote_actor_id: "user-editor",
        remote_actor_type: "USER",
        remote_result_version_id: remoteVersion,
        node_id: local.node_id,
        property_name: local.property_name,
      }],
      rebased: true,
    });
  }

  openRealtime(_projectId: string, _documentId: string, listener: (event: CollaborationRealtimeEvent) => void): CollaborationRealtimeConnection {
    queueMicrotask(() => {
      listener({ type: "CONNECTED" });
      listener({ type: "PRESENCE_SNAPSHOT", presence: clone(this.#workspace.presence) });
    });
    return { close() {} };
  }

  #thread(threadId: string): CollaborationThread {
    const thread = this.#workspace.threads.find((item) => item.thread_id === threadId);
    if (!thread) throw new Error("COLLABORATION_THREAD_NOT_FOUND");
    return thread;
  }

  #replaceThread(thread: CollaborationThread): void {
    this.#workspace = {
      ...this.#workspace,
      threads: this.#workspace.threads.map((item) => item.thread_id === thread.thread_id ? thread : item),
    };
  }

  #assert(projectId: string, documentId: string, signal?: AbortSignal): void {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (projectId !== this.#workspace.project_id || documentId !== this.#workspace.document_id) {
      throw new Error("COLLABORATION_PROJECT_NOT_FOUND");
    }
  }
}

export function createCollaborationGateway(bootstrap: CollaborationBootstrap): CollaborationGateway {
  if (bootstrap.mode === "DETERMINISTIC" && bootstrap.workspace) {
    return new DeterministicCollaborationGateway(bootstrap.workspace);
  }
  return new HttpCollaborationGateway();
}
