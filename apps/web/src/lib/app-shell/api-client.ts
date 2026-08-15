import type { ProblemDetails } from "./types";

export interface ApiClientContext {
  readonly organization_id?: string;
  readonly csrf_token?: string;
}

export interface ApiRequestOptions {
  readonly signal?: AbortSignal;
  readonly headers?: Readonly<Record<string, string>>;
  readonly idempotency_key?: string;
  readonly if_match?: string;
}

export class LumiApiError extends Error {
  readonly problem: ProblemDetails;

  constructor(problem: ProblemDetails) {
    super(problem.code);
    this.name = "LumiApiError";
    this.problem = problem;
  }
}

function requestId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function isProblemDetails(value: unknown): value is ProblemDetails {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.type === "string" &&
    typeof candidate.title === "string" &&
    typeof candidate.status === "number" &&
    typeof candidate.code === "string"
  );
}

async function parseProblem(
  response: Response,
  fallbackRequestId: string,
): Promise<ProblemDetails> {
  let value: unknown;
  try {
    value = await response.json();
  } catch {
    value = null;
  }

  if (isProblemDetails(value)) return value;
  return {
    type: "about:blank",
    title: "Request failed",
    status: response.status,
    code: "HTTP_REQUEST_FAILED",
    request_id: response.headers.get("x-request-id") ?? fallbackRequestId,
  };
}

const RETRYABLE_STATUS = new Set([502, 503, 504]);

export class LumiApiClient {
  readonly #baseUrl: string;
  readonly #transport: typeof fetch;
  readonly #context: () => ApiClientContext;

  constructor(
    options: {
      readonly base_url?: string;
      readonly transport?: typeof fetch;
      readonly context?: () => ApiClientContext;
    } = {},
  ) {
    this.#baseUrl = options.base_url ?? "/api/v1";
    this.#transport = options.transport ?? globalThis.fetch.bind(globalThis);
    this.#context = options.context ?? (() => ({}));
  }

  get<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
    return this.#request<T>("GET", path, undefined, options);
  }

  post<TResponse, TBody>(
    path: string,
    body: TBody,
    options: ApiRequestOptions = {},
  ): Promise<TResponse> {
    return this.#request<TResponse>("POST", path, body, options);
  }

  patch<TResponse, TBody>(
    path: string,
    body: TBody,
    options: ApiRequestOptions = {},
  ): Promise<TResponse> {
    return this.#request<TResponse>("PATCH", path, body, options);
  }

  async #request<T>(
    method: "GET" | "POST" | "PATCH",
    path: string,
    body: unknown,
    options: ApiRequestOptions,
  ): Promise<T> {
    const context = this.#context();
    const id = requestId();
    const headers = new Headers(options.headers);
    headers.set("accept", "application/json");
    headers.set("x-request-id", id);
    if (context.organization_id) {
      headers.set("x-lumi-organization-id", context.organization_id);
    }
    if (options.if_match) headers.set("if-match", options.if_match);
    if (options.idempotency_key) {
      headers.set("idempotency-key", options.idempotency_key);
    }
    if (method !== "GET") {
      headers.set("content-type", "application/json");
      if (context.csrf_token) {
        headers.set("x-csrf-token", context.csrf_token);
      }
    }

    const attempts = method === "GET" ? 3 : 1;
    let lastNetworkError: unknown;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        const init: RequestInit = {
          method,
          credentials: "same-origin",
          headers,
          ...(options.signal ? { signal: options.signal } : {}),
          ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        };
        const response = await this.#transport(`${this.#baseUrl}${path}`, init);
        if (response.ok) {
          if (response.status === 204) return undefined as T;
          return (await response.json()) as T;
        }
        if (
          method === "GET" &&
          RETRYABLE_STATUS.has(response.status) &&
          attempt + 1 < attempts
        ) {
          continue;
        }
        throw new LumiApiError(await parseProblem(response, id));
      } catch (error) {
        if (error instanceof LumiApiError) throw error;
        if (options.signal?.aborted) throw error;
        lastNetworkError = error;
        if (method !== "GET" || attempt + 1 >= attempts) break;
      }
    }

    const problem: ProblemDetails = {
      type: "https://errors.lumi.dev/network/unavailable",
      title: "Network unavailable",
      status: 503,
      code: "NETWORK_UNAVAILABLE",
      request_id: id,
      ...(lastNetworkError instanceof Error
        ? { detail: lastNetworkError.name }
        : {}),
    };
    throw new LumiApiError(problem);
  }
}
