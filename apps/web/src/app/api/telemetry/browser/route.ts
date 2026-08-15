import { sanitizeBrowserTelemetry } from "../../../../lib/observability/browser";

const MAX_TELEMETRY_BODY = 8 * 1024;

export async function POST(request: Request): Promise<Response> {
  const contentType = request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (contentType !== "application/json") {
    return Response.json({ detail: "unsupported media type" }, { status: 415 });
  }

  const contentLength = request.headers.get("content-length");
  if (contentLength) {
    const parsed = Number(contentLength);
    if (!Number.isFinite(parsed) || parsed < 0) {
      return Response.json({ detail: "invalid content-length" }, { status: 400 });
    }
    if (parsed > MAX_TELEMETRY_BODY) {
      return Response.json({ detail: "telemetry payload too large" }, { status: 413 });
    }
  }

  const requestOrigin = new URL(request.url).origin;
  const origin = request.headers.get("origin");
  if (origin && origin !== requestOrigin) {
    return Response.json({ detail: "cross-origin telemetry forbidden" }, { status: 403 });
  }
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite && fetchSite !== "same-origin") {
    return Response.json({ detail: "cross-site telemetry forbidden" }, { status: 403 });
  }

  let body: unknown;
  try {
    const raw = await request.text();
    if (new TextEncoder().encode(raw).byteLength > MAX_TELEMETRY_BODY) {
      return Response.json({ detail: "telemetry payload too large" }, { status: 413 });
    }
    body = JSON.parse(raw);
  } catch {
    return Response.json({ detail: "invalid telemetry payload" }, { status: 400 });
  }

  const event = sanitizeBrowserTelemetry(body);
  if (!event) {
    return Response.json({ detail: "invalid telemetry event" }, { status: 422 });
  }

  const logRecord = {
    timestamp: new Date().toISOString(),
    level: event.kind.endsWith("error") || event.kind === "api_failure" ? "WARN" : "INFO",
    service: "web",
    event: `browser.${event.kind}`,
    browser_event: event.name,
    route: event.route,
    ...(event.value === undefined ? {} : { value: event.value }),
    ...(event.statusClass ? { status_class: event.statusClass } : {}),
    ...(event.requestId ? { request_id: event.requestId } : {}),
    ...(event.correlationId ? { correlation_id: event.correlationId } : {}),
    ...(event.errorCode ? { error_code: event.errorCode } : {}),
  };
  console.info(JSON.stringify(logRecord));

  return new Response(null, {
    status: 204,
    headers: {
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}
