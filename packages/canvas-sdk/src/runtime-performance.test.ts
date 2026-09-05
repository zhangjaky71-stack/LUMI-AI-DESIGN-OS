import { describe, expect, it } from "vitest";

import {
  CANVAS_SYNC_FRAME_BUDGET_MS,
  runCanvasRuntimeBenchmark,
} from "./runtime-benchmark";

describe("NODE-40 synchronous frame-work budget", () => {
  it("keeps the 2k mixed scene spatial workload under the NODE-08 16.7ms budget", () => {
    const result = runCanvasRuntimeBenchmark(2_000, 80);
    expect(result.visible_mean).toBeGreaterThan(0);
    expect(result.budget_ms).toBe(CANVAS_SYNC_FRAME_BUDGET_MS);
    expect(result.p95_ms).toBeLessThanOrEqual(CANVAS_SYNC_FRAME_BUDGET_MS);
    expect(result.within_budget).toBe(true);
  });

  it("keeps the bounded 10k stress spatial workload under the same synchronous budget", () => {
    const result = runCanvasRuntimeBenchmark(10_000, 80);
    expect(result.visible_mean).toBeGreaterThan(0);
    expect(result.p95_ms).toBeLessThanOrEqual(CANVAS_SYNC_FRAME_BUDGET_MS);
    expect(result.within_budget).toBe(true);
  });

  it("has a deterministic clock seam without claiming headless rAF FPS", () => {
    let time = 0;
    const result = runCanvasRuntimeBenchmark(2_000, 10, () => {
      time += 0.25;
      return time;
    });
    expect(result.p95_ms).toBe(0.25);
    expect(result.mean_ms).toBe(0.25);
  });
});
