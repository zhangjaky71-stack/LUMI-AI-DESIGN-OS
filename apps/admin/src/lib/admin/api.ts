import {
  parseAdminDashboard,
  parseDeadLetters,
  parseFeatureFlags,
  parsePlatformAdminPrincipal,
  parseProviders,
  parseSafeRuns,
  type AdminDashboard,
  type FeatureFlag,
  type PlatformAdminPrincipal,
  type ProviderControlSummary,
  type SafeDeadLetter,
  type SafeRunSummary,
} from "./types";

const API_ORIGIN = (process.env.NEXT_PUBLIC_LUMI_API_ORIGIN ?? "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);

export class AdminApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null,
  ) {
    super(message);
    this.name = "AdminApiError";
  }
}

function csrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("lumi_csrf="));
  return match ? decodeURIComponent(match.slice("lumi_csrf=".length)) : null;
}

async function request(
  organizationId: string,
  path: string,
  init: RequestInit = {},
): Promise<unknown> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Organization-ID", organizationId);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = csrfToken();
    if (!csrf) throw new AdminApiError("CSRF token is unavailable", 0, "csrf_missing");
    headers.set("X-CSRF-Token", csrf);
  }

  const response = await fetch(`${API_ORIGIN}${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
    cache: "no-store",
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String((payload as { detail?: unknown }).detail ?? `HTTP ${response.status}`)
        : `HTTP ${response.status}`;
    const code =
      typeof payload === "object" && payload !== null && "code" in payload
        ? String((payload as { code?: unknown }).code ?? "") || null
        : null;
    throw new AdminApiError(detail, response.status, code);
  }
  return payload;
}

async function permissionScoped<T>(operation: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 403) return fallback;
    throw error;
  }
}

export async function loadAdminPrincipal(organizationId: string): Promise<PlatformAdminPrincipal> {
  return parsePlatformAdminPrincipal(await request(organizationId, "/api/v1/admin/me"));
}

export async function loadAdminDashboard(organizationId: string): Promise<AdminDashboard> {
  return parseAdminDashboard(await request(organizationId, "/api/v1/admin/dashboard"));
}

export async function loadFailingRuns(organizationId: string): Promise<SafeRunSummary[]> {
  return permissionScoped(
    async () => parseSafeRuns(await request(organizationId, "/api/v1/admin/runs/failing?limit=50")),
    [],
  );
}

export async function loadDeadLetters(organizationId: string): Promise<SafeDeadLetter[]> {
  return parseDeadLetters(await request(organizationId, "/api/v1/admin/dlq?limit=50"));
}

export async function loadProviders(organizationId: string): Promise<ProviderControlSummary[]> {
  return permissionScoped(
    async () => parseProviders(await request(organizationId, "/api/v1/admin/providers?limit=100")),
    [],
  );
}

export async function loadFeatureFlags(organizationId: string): Promise<FeatureFlag[]> {
  return parseFeatureFlags(await request(organizationId, "/api/v1/admin/feature-flags"));
}

export async function replayDeadLetter(
  organizationId: string,
  deadLetterId: string,
  reason: string,
): Promise<void> {
  await request(organizationId, `/api/v1/admin/dlq/${encodeURIComponent(deadLetterId)}/replay`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export async function discardDeadLetter(
  organizationId: string,
  deadLetterId: string,
  reason: string,
): Promise<void> {
  await request(organizationId, `/api/v1/admin/dlq/${encodeURIComponent(deadLetterId)}/discard`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export async function setProviderOverride(
  organizationId: string,
  input: {
    provider: string;
    model: string | null;
    capability: string | null;
    action: "force_disabled" | "force_degraded" | "clear_override" | "clear_breaker";
    reason: string;
  },
): Promise<void> {
  await request(organizationId, "/api/v1/admin/providers/override", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
