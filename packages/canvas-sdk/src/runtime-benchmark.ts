import type { DesignDocument, DesignNode } from "../../design-ir/src/index";
import { projectDesignDocument } from "./ir-scene";
import { CanvasSpatialIndex } from "./spatial-index";
import type { Rect } from "./types";

export const CANVAS_SYNC_FRAME_BUDGET_MS = 16.7;

export interface CanvasRuntimeBenchmarkResult {
  readonly node_count: number;
  readonly iterations: number;
  readonly visible_mean: number;
  readonly p50_ms: number;
  readonly p95_ms: number;
  readonly mean_ms: number;
  readonly budget_ms: number;
  readonly within_budget: boolean;
}

function percentile(values: readonly number[], p: number): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * p) - 1));
  return sorted[index] ?? 0;
}

export function createMixedDesignDocument(nodeCount: number): DesignDocument {
  const count = Math.max(4, Math.floor(nodeCount));
  const frameCount = 4;
  const nodes: Record<string, DesignNode> = {
    root: {
      id: "root",
      kind: "DOCUMENT_ROOT",
      parent_id: null,
      children: Array.from({ length: frameCount }, (_, index) => `frame-${index}`),
    },
  };
  const perFrame = Math.ceil((count - frameCount - 1) / frameCount);
  let created = 1;
  for (let frameIndex = 0; frameIndex < frameCount && created < count; frameIndex += 1) {
    const frameId = `frame-${frameIndex}`;
    const children: string[] = [];
    nodes[frameId] = {
      id: frameId,
      kind: "FRAME",
      parent_id: "root",
      children,
      transform: {
        x: (frameIndex % 2) * 1800,
        y: Math.floor(frameIndex / 2) * 1400,
        width: 1600,
        height: 1200,
      },
    };
    created += 1;
    for (let local = 0; local < perFrame && created < count; local += 1) {
      const id = `node-${created}`;
      const kindIndex = local % 4;
      const kind = kindIndex === 0 ? "TEXT" : kindIndex === 1 ? "IMAGE" : kindIndex === 2 ? "SHAPE" : "VECTOR_PATH";
      const column = local % 25;
      const row = Math.floor(local / 25);
      children.push(id);
      nodes[id] = {
        id,
        kind,
        parent_id: frameId,
        children: [],
        transform: {
          x: column * 62,
          y: row * 54,
          width: kind === "TEXT" ? 150 : 48,
          height: kind === "TEXT" ? 32 : 48,
        },
        ...(kind === "TEXT" ? { content: `Node ${created}` } : {}),
        ...(kind === "IMAGE" ? { asset_id: `asset-${created % 100}` } : {}),
      };
      created += 1;
    }
  }
  return {
    schema_version: "1.0",
    document_id: `benchmark-${count}`,
    unit: "px",
    root_id: "root",
    nodes,
    resources: {},
    metadata: { document_version: 1 },
  };
}

export function runCanvasRuntimeBenchmark(
  nodeCount: number,
  iterations = 120,
  now: () => number = () => performance.now(),
): CanvasRuntimeBenchmarkResult {
  const scene = projectDesignDocument(createMixedDesignDocument(nodeCount));
  const index = new CanvasSpatialIndex();
  index.rebuild(scene);
  const samples: number[] = [];
  let visibleTotal = 0;

  for (let iteration = 0; iteration < iterations; iteration += 1) {
    const viewport: Rect = {
      x: (iteration * 31) % 2200,
      y: (iteration * 19) % 1700,
      width: 1440,
      height: 900,
    };
    const started = now();
    visibleTotal += index.query(viewport).length;
    samples.push(Math.max(0, now() - started));
  }

  const p50 = percentile(samples, 0.5);
  const p95 = percentile(samples, 0.95);
  const mean = samples.reduce((sum, value) => sum + value, 0) / Math.max(1, samples.length);
  return {
    node_count: nodeCount,
    iterations,
    visible_mean: visibleTotal / Math.max(1, iterations),
    p50_ms: p50,
    p95_ms: p95,
    mean_ms: mean,
    budget_ms: CANVAS_SYNC_FRAME_BUDGET_MS,
    within_budget: p95 <= CANVAS_SYNC_FRAME_BUDGET_MS,
  };
}
