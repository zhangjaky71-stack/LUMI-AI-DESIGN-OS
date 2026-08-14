import type { RepairAttemptRecord, RepairLoopResult } from "./types";

export interface AutoRepairTelemetry {
  readonly loop_id: string;
  readonly status: string;
  readonly iterations: number;
  readonly spent_usd: string;
  readonly attempt_count: number;
  readonly promoted_ready_count: number;
  readonly promoted_draft_count: number;
  readonly rejected_count: number;
  readonly action_kinds: readonly string[];
  readonly reason_codes: readonly string[];
}

export function autoRepairTelemetry(result: RepairLoopResult): AutoRepairTelemetry {
  return {
    loop_id: result.loop_id,
    status: result.status,
    iterations: result.iterations,
    spent_usd: result.spent_usd,
    attempt_count: result.attempts.length,
    promoted_ready_count: result.attempts.filter((item) => item.disposition === "PROMOTED_READY").length,
    promoted_draft_count: result.attempts.filter((item) => item.disposition === "PROMOTED_DRAFT").length,
    rejected_count: result.attempts.filter((item) => item.disposition === "REJECTED").length,
    action_kinds: [...new Set(result.attempts.map((item) => item.action_kind))].sort(),
    reason_codes: [...new Set([...result.reason_codes, ...result.attempts.flatMap((item: RepairAttemptRecord) => item.reason_codes)])].sort(),
  };
}
