import { describe, expect, it } from "vitest";

import { runCanvasCompilerBenchmark } from "./compiler-benchmark";

describe("NODE-41 compiler benchmark harness", () => {
  it("compiles 2k nodes and 100 operations with incremental/full hash equivalence", async () => {
    let clock = 0;
    const result = await runCanvasCompilerBenchmark(2_000, 100, () => {
      clock += 0.25;
      return clock;
    });
    expect(result.node_count).toBe(2_000);
    expect(result.operation_count).toBe(100);
    expect(result.fallback_to_full).toBe(false);
    expect(result.equivalent_compile_hash).toBe(true);
    expect(result.dirty_node_count).toBeGreaterThanOrEqual(100);
    expect(result.dirty_node_count).toBeLessThan(result.node_count);
    expect(result.upserted_node_count).toBeLessThan(result.node_count);
    expect(result.full_compile_ms).toBeGreaterThan(0);
    expect(result.incremental_compile_ms).toBeGreaterThan(0);
  });
});
