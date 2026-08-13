from __future__ import annotations

from pathlib import Path


RUNTIME = Path("apps/web/src/app/canvas-spike/pixi-runtime.ts")


def main() -> None:
    text = RUNTIME.read_text(encoding="utf-8")

    text = text.replace(
        "export interface ScreenRect extends Rect {}",
        "export type ScreenRect = Rect;",
    )
    text = text.replace("  createGridNodes,\n", "")

    benchmark_import = (
        'import { runVirtualizedCanvasBenchmark } from "./virtualized-benchmark";\n\n'
    )
    canvas_import_end = '} from "@lumi/canvas-sdk";\n\n'
    if benchmark_import not in text:
        text = text.replace(canvas_import_end, canvas_import_end + benchmark_import, 1)

    percentile_start = text.find("function percentile(")
    distance_start = text.find("function distance(")
    if percentile_start >= 0 and distance_start > percentile_start:
        text = text[:percentile_start] + text[distance_start:]

    run_start = text.find(
        "  async runBenchmark(): Promise<CanvasSpikeBenchmarkReport> {"
    )
    old_helpers_start = text.find("  async #frameSamples(", run_start)
    if run_start >= 0 and old_helpers_start > run_start:
        replacement = """  async runBenchmark(): Promise<CanvasSpikeBenchmarkReport> {
    const app = this.#app;
    const pixi = this.#pixi;
    if (!app || !pixi) {
      throw new Error(\"canvas spike is not ready\");
    }
    return runVirtualizedCanvasBenchmark(pixi, app);
  }
"""
        text = text[:run_start] + replacement + "}\n"

    RUNTIME.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
