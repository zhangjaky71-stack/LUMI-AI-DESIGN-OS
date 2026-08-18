import { describe, expect, it } from "vitest";

import { consumeSse } from "./stream";

function stream(text: string): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream<Uint8Array>({
    start(controller) {
      const midpoint = Math.floor(bytes.length / 2);
      controller.enqueue(bytes.slice(0, midpoint));
      controller.enqueue(bytes.slice(midpoint));
      controller.close();
    },
  });
}

function payload(eventId: string, message: string): string {
  return JSON.stringify({
    event_id: eventId,
    event_type: "agent.status",
    agent_run_id: "run-1",
    project_id: "project-1",
    occurred_at: "2026-08-18T00:00:00Z",
    payload: { message },
  });
}

describe("SSE consumer", () => {
  it("handles split chunks, remembers cursor, and deduplicates replay", async () => {
    const received: string[] = [];
    const body = stream(
      `id: evt-1\nevent: agent.status\ndata: ${payload("evt-1", "one")}\n\n` +
      `id: evt-1\nevent: agent.status\ndata: ${payload("evt-1", "one replay")}\n\n` +
      `id: evt-2\nevent: agent.status\ndata: ${payload("evt-2", "two")}\n\n`,
    );

    const last = await consumeSse(body, {
      onEvent: (event) => received.push(event.eventId),
    });

    expect(received).toEqual(["evt-1", "evt-2"]);
    expect(last).toBe("evt-2");
  });

  it("does not emit the supplied Last-Event-ID again", async () => {
    const received: string[] = [];
    const last = await consumeSse(
      stream(`id: evt-9\ndata: ${payload("evt-9", "replay")}\n\n`),
      { lastEventId: "evt-9", onEvent: (event) => received.push(event.eventId) },
    );
    expect(received).toEqual([]);
    expect(last).toBe("evt-9");
  });
});
