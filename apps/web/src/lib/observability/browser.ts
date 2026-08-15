export type BrowserTelemetryKind =
  | "api_failure"
  | "canvas_error"
  | "route_error"
  | "runtime_error"
  | "web_vital";

export type WebVitalName = "cls" | "inp_ms" | "lcp_ms" | "ttfb_ms";

export interface BrowserTelemetryEvent {
  version: 1;
  kind: BrowserTelemetryKind;
  name: string;
  route: string;
  value?: number;
  statusClass?: string;
  requestId?: string;
  correlationId?: string;
  errorCode?: string;
}

export interface BrowserTelemetryOptions {
  endpoint?: string;
  sampleRate?: number;
  random?: () => number;
}

const SAFE_REF = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SAFE_NAME = /^[a-z][a-z0-9_.-]{0,63}$/;
const STATUS_CLASS = /^[1-5]xx$/;
const UUID_SEGMENT = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const OPAQUE_ID_SEGMENT = /^(?:[0-9a-f]{24,64}|[0-9]{4,}|[0-9A-HJKMNP-TV-Z]{26})$/i;
const MAX_BODY_BYTES = 4096;

export function safeTelemetryRef(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  const candidate = value.trim();
  return SAFE_REF.test(candidate) ? candidate : undefined;
}

export function normalizeTelemetryRoute(value: string): string {
  let pathname = value;
  try {
    pathname = new URL(value, "https://lumi.invalid").pathname;
  } catch {
    pathname = value.split(/[?#]/, 1)[0] ?? "/";
  }
  const normalized = pathname
    .split("/")
    .map((segment) => {
      if (!segment) return segment;
      if (UUID_SEGMENT.test(segment) || OPAQUE_ID_SEGMENT.test(segment)) return ":id";
      return segment.slice(0, 80);
    })
    .join("/");
  return (normalized || "/").slice(0, 240);
}

export function sanitizeBrowserTelemetry(input: unknown): BrowserTelemetryEvent | null {
  if (!input || typeof input !== "object" || Array.isArray(input)) return null;
  const raw = input as Record<string, unknown>;
  const kind = raw.kind;
  if (!isTelemetryKind(kind)) return null;
  if (raw.version !== 1) return null;
  if (typeof raw.name !== "string" || !SAFE_NAME.test(raw.name)) return null;
  if (typeof raw.route !== "string") return null;

  const event: BrowserTelemetryEvent = {
    version: 1,
    kind,
    name: raw.name,
    route: normalizeTelemetryRoute(raw.route),
  };

  if (typeof raw.value === "number" && Number.isFinite(raw.value) && raw.value >= 0) {
    event.value = Math.min(raw.value, 86_400_000);
  }
  if (typeof raw.statusClass === "string" && STATUS_CLASS.test(raw.statusClass)) {
    event.statusClass = raw.statusClass;
  }
  if (typeof raw.requestId === "string") {
    event.requestId = safeTelemetryRef(raw.requestId);
  }
  if (typeof raw.correlationId === "string") {
    event.correlationId = safeTelemetryRef(raw.correlationId);
  }
  if (typeof raw.errorCode === "string") {
    const code = raw.errorCode.trim().toLowerCase();
    if (SAFE_NAME.test(code)) event.errorCode = code;
  }
  return event;
}

export function emitBrowserTelemetry(
  input: BrowserTelemetryEvent,
  options: BrowserTelemetryOptions = {},
): boolean {
  if (typeof window === "undefined" || typeof navigator === "undefined") return false;
  const event = sanitizeBrowserTelemetry(input);
  if (!event) return false;

  const sampleRate = clampSampleRate(options.sampleRate ?? defaultSampleRate(event.kind));
  const random = options.random ?? Math.random;
  if (sampleRate < 1 && random() >= sampleRate) return false;

  const body = JSON.stringify(event);
  if (new TextEncoder().encode(body).byteLength > MAX_BODY_BYTES) return false;
  const endpoint = options.endpoint ?? "/api/telemetry/browser";

  try {
    if (typeof navigator.sendBeacon === "function") {
      return navigator.sendBeacon(endpoint, new Blob([body], { type: "application/json" }));
    }
    void fetch(endpoint, {
      method: "POST",
      body,
      headers: { "content-type": "application/json" },
      credentials: "same-origin",
      keepalive: true,
    }).catch(() => undefined);
    return true;
  } catch {
    return false;
  }
}

export function reportRouteError(errorCode?: string, route = currentRoute()): boolean {
  return emitBrowserTelemetry({
    version: 1,
    kind: "route_error",
    name: "react_route_error",
    route,
    errorCode: safeErrorCode(errorCode),
  });
}

export function reportCanvasError(errorCode?: string, route = currentRoute()): boolean {
  return emitBrowserTelemetry({
    version: 1,
    kind: "canvas_error",
    name: "canvas_runtime_error",
    route,
    errorCode: safeErrorCode(errorCode),
  });
}

export function reportWebVital(name: WebVitalName, value: number, route = currentRoute()): boolean {
  return emitBrowserTelemetry(
    { version: 1, kind: "web_vital", name, route, value },
    { sampleRate: 0.1 },
  );
}

export async function observedFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    const target = input instanceof Request ? input.url : String(input);
    emitBrowserTelemetry({
      version: 1,
      kind: "api_failure",
      name: `api_${method.toLowerCase()}_failed`,
      route: target,
      statusClass: `${Math.floor(response.status / 100)}xx`,
      requestId: safeTelemetryRef(response.headers.get("x-request-id")),
      correlationId: safeTelemetryRef(response.headers.get("x-correlation-id")),
    });
  }
  return response;
}

export function responseCorrelation(response: Response): {
  requestId?: string;
  correlationId?: string;
} {
  return {
    requestId: safeTelemetryRef(response.headers.get("x-request-id")),
    correlationId: safeTelemetryRef(response.headers.get("x-correlation-id")),
  };
}

function currentRoute(): string {
  return typeof window === "undefined" ? "/" : normalizeTelemetryRoute(window.location.pathname);
}

function safeErrorCode(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const normalized = value.trim().toLowerCase().replace(/[^a-z0-9_.-]+/g, "_").slice(0, 64);
  return SAFE_NAME.test(normalized) ? normalized : undefined;
}

function defaultSampleRate(kind: BrowserTelemetryKind): number {
  return kind === "web_vital" ? 0.1 : 1;
}

function clampSampleRate(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(Math.max(value, 0), 1);
}

function isTelemetryKind(value: unknown): value is BrowserTelemetryKind {
  return (
    value === "api_failure" ||
    value === "canvas_error" ||
    value === "route_error" ||
    value === "runtime_error" ||
    value === "web_vital"
  );
}
