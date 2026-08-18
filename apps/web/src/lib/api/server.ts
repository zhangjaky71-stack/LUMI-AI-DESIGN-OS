import { cookies, headers as requestHeaders } from "next/headers";

import {
  apiErrorFromResponse,
  readResponseBody,
  unwrapData,
} from "@/lib/api/problem";
import { getWebRuntimeConfig, requireApiPath } from "@/lib/config/env";

export type ServerApiRequestOptions = Omit<RequestInit, "body" | "cache"> & {
  body?: BodyInit | null;
  json?: unknown;
};

export async function serverApiRequest<T>(
  path: string,
  options: ServerApiRequestOptions = {},
): Promise<T> {
  requireApiPath(path);
  if (options.body !== undefined && options.json !== undefined) {
    throw new Error("Server API request cannot provide both body and json");
  }

  const config = getWebRuntimeConfig();
  const cookieStore = await cookies();
  const incomingHeaders = await requestHeaders();
  const headers = new Headers(options.headers);
  headers.set("accept", "application/json");

  const cookieHeader = cookieStore
    .getAll()
    .map(({ name, value }) => `${name}=${value}`)
    .join("; ");
  if (cookieHeader) headers.set("cookie", cookieHeader);
  headers.set(
    "x-request-id",
    incomingHeaders.get("x-request-id") ?? crypto.randomUUID(),
  );

  let body = options.body;
  if (options.json !== undefined) {
    headers.set("content-type", "application/json");
    body = JSON.stringify(options.json);
  }

  const response = await fetch(`${config.apiOrigin}${path}`, {
    ...options,
    headers,
    body,
    cache: "no-store",
    redirect: "manual",
  });
  const payload = await readResponseBody(response);
  if (!response.ok) throw apiErrorFromResponse(response, payload);
  return unwrapData<T>(payload);
}
