import { parseSafeRunEvent, type SafeRunEvent } from "@/lib/workspace/types";
import { tenantHeaders } from "@/lib/workspace/api";

export type WorkspaceConnectionState =
  | "connecting"
  | "live"
  | "reconnecting"
  | "disconnected";

export type RunEventStreamOptions = {
  organizationId: string;
  agentRunId: string;
  signal: AbortSignal;
  initialLastEventId?: string | null;
  onEvent: (event: SafeRunEvent) => void;
  onState?: (state: WorkspaceConnectionState) => void;
  onStreamEnd?: (lastEventId: string | null) => Promise<void> | void;
  fetcher?: typeof fetch;
};

export async function connectRunEventStream(options: RunEventStreamOptions): Promise<void> {
  const fetcher = options.fetcher ?? fetch;
  let lastEventId = options.initialLastEventId ?? null;
  let reconnectAttempt = 0;

  while (!options.signal.aborted) {
    options.onState?.(reconnectAttempt === 0 ? "connecting" : "reconnecting");
    try {
      const headers = tenantHeaders(options.organizationId, {
        Accept: "text/event-stream",
        ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
      });
      const response = await fetcher(
        `/api/v1/agent-runs/${encodeURIComponent(options.agentRunId)}/events`,
        {
          method: "GET",
          headers,
          credentials: "include",
          cache: "no-store",
          signal: options.signal,
        },
      );
      if (!response.ok || !response.body) {
        throw new Error(`RUN_EVENT_STREAM_HTTP_${response.status}`);
      }
      options.onState?.("live");
      lastEventId = await consumeSse(response.body, {
        lastEventId,
        onEvent: options.onEvent,
        signal: options.signal,
      });
      await options.onStreamEnd?.(lastEventId);
      if (options.signal.aborted) break;
      reconnectAttempt += 1;
      options.onState?.("reconnecting");
      await abortableSleep(reconnectDelay(reconnectAttempt), options.signal);
    } catch (error) {
      if (options.signal.aborted || isAbortError(error)) break;
      await options.onStreamEnd?.(lastEventId);
      reconnectAttempt += 1;
      options.onState?.("reconnecting");
      await abortableSleep(reconnectDelay(reconnectAttempt), options.signal);
    }
  }
  options.onState?.("disconnected");
}

export async function consumeSse(
  body: ReadableStream<Uint8Array>,
  options: {
    lastEventId?: string | null;
    onEvent: (event: SafeRunEvent) => void;
    signal?: AbortSignal;
  },
): Promise<string | null> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let lastEventId = options.lastEventId ?? null;
  const seen = new Set<string>();
  if (lastEventId) seen.add(lastEventId);

  try {
    while (!options.signal?.aborted) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsed = parseFrame(frame);
        if (parsed?.data) {
          const event = parseSafeRunEvent(JSON.parse(parsed.data));
          const eventId = parsed.id ?? event.eventId;
          if (eventId !== event.eventId) throw new Error("RUN_EVENT_ID_MISMATCH");
          if (!seen.has(eventId)) {
            seen.add(eventId);
            options.onEvent(event);
          }
          lastEventId = eventId;
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
  return lastEventId;
}

type ParsedFrame = { id?: string; event?: string; data?: string };

function parseFrame(frame: string): ParsedFrame | null {
  const result: ParsedFrame = {};
  const data: string[] = [];
  for (const line of frame.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon >= 0 ? line.slice(0, colon) : line;
    let value = colon >= 0 ? line.slice(colon + 1) : "";
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "id") result.id = value;
    else if (field === "event") result.event = value;
    else if (field === "data") data.push(value);
  }
  if (data.length) result.data = data.join("\n");
  return Object.keys(result).length ? result : null;
}

function reconnectDelay(attempt: number): number {
  return Math.min(8_000, 500 * 2 ** Math.min(attempt - 1, 4));
}

function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  );
}

async function abortableSleep(ms: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return;
  await new Promise<void>((resolve) => {
    const timer = setTimeout(done, ms);
    signal.addEventListener("abort", done, { once: true });
    function done() {
      clearTimeout(timer);
      signal.removeEventListener("abort", done);
      resolve();
    }
  });
}
