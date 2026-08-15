import { executeOperations, getDocumentVersion, type DesignOperation } from "@lumi/design-ir";
import { LumiApiClient, LumiApiError } from "@/lib/app-shell/api-client";
import type {
  InfiniteCanvasBootstrap,
  InfiniteCanvasSeed,
  InfiniteCanvasSnapshot,
  SaveCanvasOperationsInput,
} from "./types";

export interface InfiniteCanvasGateway {
  getDocument(
    organizationId: string,
    projectId: string,
    signal?: AbortSignal,
  ): Promise<InfiniteCanvasSnapshot>;
  saveOperations(
    organizationId: string,
    input: SaveCanvasOperationsInput,
    signal?: AbortSignal,
  ): Promise<InfiniteCanvasSnapshot>;
}

function problem(code: string, status = 409): LumiApiError {
  return new LumiApiError({
    type: `https://errors.lumi.dev/infinite-canvas/${code.toLowerCase().replaceAll("_", "-")}`,
    title: code,
    status,
    code,
    request_id: `canvas-${code.toLowerCase()}`,
  });
}

function requestOptions(signal?: AbortSignal): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

function validateSave(input: SaveCanvasOperationsInput): SaveCanvasOperationsInput {
  if (!input.project_id || !input.document_id) throw problem("CANVAS_SCOPE_REQUIRED", 400);
  if (!Number.isSafeInteger(input.expected_document_version) || input.expected_document_version < 0) {
    throw problem("DOCUMENT_VERSION_INVALID", 400);
  }
  if (!input.operations.length) throw problem("DESIGN_OPERATIONS_REQUIRED", 400);
  if (
    input.operations.some(
      (operation) => operation.expected_document_version !== input.expected_document_version,
    )
  ) {
    throw problem("DESIGN_OPERATION_VERSION_MISMATCH", 400);
  }
  return input;
}

export class HttpInfiniteCanvasGateway implements InfiniteCanvasGateway {
  readonly #api: LumiApiClient;

  constructor(api: LumiApiClient) {
    this.#api = api;
  }

  getDocument(_organizationId: string, projectId: string, signal?: AbortSignal) {
    return this.#api.get<InfiniteCanvasSnapshot>(
      `/projects/${encodeURIComponent(projectId)}/canvas-document`,
      requestOptions(signal),
    );
  }

  saveOperations(
    _organizationId: string,
    input: SaveCanvasOperationsInput,
    signal?: AbortSignal,
  ) {
    const safe = validateSave(input);
    return this.#api.post<InfiniteCanvasSnapshot, SaveCanvasOperationsInput>(
      `/canvas/documents/${encodeURIComponent(safe.document_id)}/operations:batch`,
      safe,
      { idempotency_key: crypto.randomUUID(), ...requestOptions(signal) },
    );
  }
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function externalEditOperation(documentId: string, version: number): DesignOperation {
  return {
    operation_id: `e2e-external-edit-${documentId}-${version}`,
    type: "SET_PROPERTY",
    target_ids: ["frame-square"],
    expected_document_version: version,
    payload: {
      path: "metadata.external_revision",
      value: `external-${version + 1}`,
    },
    reason: "e2e-version-conflict",
  };
}

export class DeterministicInfiniteCanvasGateway implements InfiniteCanvasGateway {
  #snapshot: InfiniteCanvasSnapshot;
  #conflictOnNextSave: boolean;

  constructor(seed: InfiniteCanvasSeed) {
    this.#snapshot = clone(seed.snapshot);
    this.#conflictOnNextSave = seed.conflict_on_next_save;
  }

  async getDocument(organizationId: string, projectId: string, signal?: AbortSignal) {
    this.#assertScope(organizationId, projectId, signal);
    return clone(this.#snapshot);
  }

  async saveOperations(
    organizationId: string,
    input: SaveCanvasOperationsInput,
    signal?: AbortSignal,
  ) {
    this.#assertScope(organizationId, input.project_id, signal);
    const safe = validateSave(input);
    const currentVersion = getDocumentVersion(this.#snapshot.document);
    if (safe.document_id !== this.#snapshot.document.document_id) {
      throw problem("DOCUMENT_NOT_FOUND", 404);
    }

    if (this.#conflictOnNextSave) {
      const external = executeOperations(this.#snapshot.document, [
        externalEditOperation(this.#snapshot.document.document_id, currentVersion),
      ]);
      if (external.ok) {
        this.#snapshot = {
          ...this.#snapshot,
          document: external.document,
          saved_at: "2026-08-15T03:12:00.000Z",
        };
      }
      this.#conflictOnNextSave = false;
      throw problem("DOCUMENT_VERSION_CONFLICT", 409);
    }

    if (safe.expected_document_version !== currentVersion) {
      throw problem("DOCUMENT_VERSION_CONFLICT", 409);
    }

    const result = executeOperations(this.#snapshot.document, safe.operations);
    if (!result.ok) {
      const failure = result.failures[0];
      throw problem(failure?.code ?? "DESIGN_OPERATION_REJECTED", 409);
    }

    this.#snapshot = {
      ...this.#snapshot,
      document: result.document,
      saved_at: new Date(
        Date.UTC(2026, 7, 15, 3, 12, result.document_version),
      ).toISOString(),
    };
    return clone(this.#snapshot);
  }

  #assertScope(organizationId: string, projectId: string, signal?: AbortSignal): void {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (organizationId !== "org-lumi" && organizationId !== "org-northstar") {
      throw problem("ORGANIZATION_FORBIDDEN", 403);
    }
    if (projectId !== this.#snapshot.project_id) throw problem("PROJECT_NOT_FOUND", 404);
  }
}

export function getInfiniteCanvasGateway(
  api: LumiApiClient,
  bootstrap: InfiniteCanvasBootstrap,
): InfiniteCanvasGateway {
  if (bootstrap.mode !== "e2e") return new HttpInfiniteCanvasGateway(api);
  if (!bootstrap.seed) throw new Error("INFINITE_CANVAS_E2E_SEED_REQUIRED");
  return new DeterministicInfiniteCanvasGateway(bootstrap.seed);
}
