import { describe, expect, it } from "vitest";

import {
  parseAdminDashboard,
  parseDeadLetters,
  parsePlatformAdminPrincipal,
  parseProviders,
} from "./types";

const now = new Date().toISOString();

describe("NODE-64 admin parsers", () => {
  it("accepts a valid platform admin principal", () => {
    expect(
      parsePlatformAdminPrincipal({
        id: "019c0000-0000-7000-8000-000000000064",
        user_id: "019c0000-0000-7000-8000-000000000001",
        role: "OPS",
        permissions: ["platform.read", "queue.manage", "provider.ops"],
        active: true,
      }).role,
    ).toBe("OPS");
  });

  it("rejects organization roles as platform admin roles", () => {
    expect(() =>
      parsePlatformAdminPrincipal({
        id: "1",
        user_id: "2",
        role: "OWNER",
        permissions: ["platform.read"],
        active: true,
      }),
    ).toThrow(/platform admin role/);
  });

  it("rejects invalid dashboard counts", () => {
    expect(() =>
      parseAdminDashboard({
        active_runs: Number.NaN,
        failed_runs: 0,
        failed_tasks: 0,
        queue_pending: 0,
        dlq_open: 0,
        degraded_providers: 0,
        payment_events_pending: 0,
        provider_cost_24h: "0",
      }),
    ).toThrow(/active_runs/);
  });

  it("keeps DLQ payload out of the safe response model", () => {
    const result = parseDeadLetters([
      {
        id: "dlq-1",
        organization_id: "org-1",
        message_id: "message-1",
        message_kind: "job",
        source_queue: "lumi.jobs",
        consumer: "worker-1",
        error_category: "transient",
        error_code: "TIMEOUT",
        error_message: "provider timeout",
        attempts: 3,
        status: "open",
        failed_at: now,
        last_failed_at: now,
        replayed_at: null,
        payload: { private_prompt: "must not be rendered" },
      },
    ]);
    expect(result).toHaveLength(1);
    expect("payload" in result[0]).toBe(false);
  });

  it("validates provider health score bounds", () => {
    expect(() =>
      parseProviders([
        {
          provider: "openai",
          model: null,
          capability: null,
          state: "healthy",
          score: 101,
          observed_at: now,
          override_action: null,
          override_expires_at: null,
        },
      ]),
    ).toThrow(/0 to 100/);
  });
});
