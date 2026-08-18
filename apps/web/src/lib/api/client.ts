import { requireApiPath } from "@/lib/config/env";
import {
  apiErrorFromResponse,
  readResponseBody,
  unwrapData,
} from "@/lib/api/problem";

export type ApiRequestOptions = Omit<RequestInit, "body"> & {
  body?: BodyInit | null;
  json?: unknown;
};

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  requireApiPath(path);
  if (options.body !== undefined && options.json !== undefined) {
    throw new Error("API request cannot provide both body and json");
  }

  const headers = new Headers(options.headers);
  if (!headers.has("accept")) headers.set("accept", "application/json");
  if (!headers.has("x-request-id")) headers.set("x-request-id", crypto.randomUUID());

  const method = (options.method ?? "GET").toUpperCase();
  if (UNSAFE_METHODS.has(method) && !headers.has("x-csrf-token")) {
    const csrf = browserCookie("lumi_csrf");
    if (csrf) headers.set("x-csrf-token", csrf);
  }

  let body = options.body;
  if (options.json !== undefined) {
    headers.set("content-type", "application/json");
    body = JSON.stringify(options.json);
  }

  const response = await fetch(path, {
    ...options,
    method,
    headers,
    body,
    credentials: "include",
  });
  const payload = await readResponseBody(response);
  if (!response.ok) throw apiErrorFromResponse(response, payload);
  return unwrapData<T>(payload);
}

export const api = {
  get<T>(path: string, options: ApiRequestOptions = {}) {
    return apiRequest<T>(path, { ...options, method: "GET" });
  },
  post<T>(path: string, json?: unknown, options: ApiRequestOptions = {}) {
    return apiRequest<T>(path, { ...options, method: "POST", json });
  },
  patch<T>(path: string, json?: unknown, options: ApiRequestOptions = {}) {
    return apiRequest<T>(path, { ...options, method: "PATCH", json });
  },
  delete<T>(path: string, options: ApiRequestOptions = {}) {
    return apiRequest<T>(path, { ...options, method: "DELETE" });
  },
};

function browserCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${encodeURIComponent(name)}=`;
  for (const rawPart of document.cookie.split(";")) {
    const part = rawPart.trim();
    if (!part.startsWith(prefix)) continue;
    try {
      return decodeURIComponent(part.slice(prefix.length));
    } catch {
      return part.slice(prefix.length);
    }
  }
  return null;
}
