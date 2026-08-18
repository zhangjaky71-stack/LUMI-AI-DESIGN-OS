export type ApiProblemPayload = {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  code?: string;
  request_id?: string;
  trace_id?: string;
  errors?: unknown;
  [key: string]: unknown;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;
  readonly traceId?: string;
  readonly problem?: ApiProblemPayload;

  constructor(args: {
    status: number;
    code: string;
    message: string;
    requestId?: string;
    traceId?: string;
    problem?: ApiProblemPayload;
  }) {
    super(args.message);
    this.name = "ApiError";
    this.status = args.status;
    this.code = args.code;
    this.requestId = args.requestId;
    this.traceId = args.traceId;
    this.problem = args.problem;
  }
}

export function apiErrorFromResponse(
  response: Response,
  payload: unknown,
): ApiError {
  const problem = isProblem(payload) ? payload : undefined;
  const requestId =
    problem?.request_id ?? response.headers.get("x-request-id") ?? undefined;
  const traceId =
    problem?.trace_id ?? response.headers.get("traceparent") ?? undefined;
  return new ApiError({
    status: response.status,
    code: problem?.code ?? `HTTP_${response.status}`,
    message:
      problem?.detail ??
      problem?.title ??
      `LUMI API request failed with status ${response.status}`,
    requestId,
    traceId,
    problem,
  });
}

export function isProblem(value: unknown): value is ApiProblemPayload {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export async function readResponseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const text = await response.text();
    return text.length ? { detail: text } : undefined;
  }
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

export function unwrapData<T>(payload: unknown): T {
  if (
    typeof payload === "object" &&
    payload !== null &&
    !Array.isArray(payload) &&
    "data" in payload
  ) {
    return (payload as { data: T }).data;
  }
  return payload as T;
}
