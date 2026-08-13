import { cullNodes } from "./geometry";
import type { Rect, SpikeNode } from "./types";

export interface CullingBenchmarkResult {
  readonly nodeCount: number;
  readonly iterations: number;
  readonly visibleMean: number;
  readonly durationMs: number;
  readonly operationsPerSecond: number;
}

export function createGridNodes(count: number, spacing = 72): SpikeNode[] {
  const columns = Math.max(1, Math.ceil(Math.sqrt(count)));
  const nodes: SpikeNode[] = [];
  for (let index = 0; index < count; index += 1) {
    const column = index % columns;
    const row = Math.floor(index / columns);
    const isText = index % 17 === 0;
    nodes.push({
      id: `stress-${index}`,
      kind: isText ? "text" : "rect",
      x: column * spacing,
      y: row * spacing,
      width: isText ? 160 : 56,
      height: isText ? 32 : 56,
      rotation: 0,
      zIndex: index,
      fill: 0x666666,
      ...(isText ? { text: `Node ${index}` } : {}),
    });
  }
  return nodes;
}

export function runCullingBenchmark(
  nodeCount: number,
  iterations = 120,
  now: () => number = () => performance.now(),
): CullingBenchmarkResult {
  const nodes = createGridNodes(nodeCount);
  const viewport: Rect = { x: 0, y: 0, width: 1440, height: 900 };
  let visibleTotal = 0;
  const started = now();
  for (let iteration = 0; iteration < iterations; iteration += 1) {
    const movedViewport = {
      ...viewport,
      x: iteration * 24,
      y: iteration * 12,
    };
    visibleTotal += cullNodes(nodes, movedViewport).length;
  }
  const durationMs = Math.max(0.001, now() - started);
  return {
    nodeCount,
    iterations,
    visibleMean: visibleTotal / iterations,
    durationMs,
    operationsPerSecond: (nodeCount * iterations * 1000) / durationMs,
  };
}
