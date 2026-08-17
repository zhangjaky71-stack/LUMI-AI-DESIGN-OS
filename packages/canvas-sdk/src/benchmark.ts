import type { DesignDocument, DesignNode } from "../../design-ir/src/index";
import { buildScene } from "./scene";
import { SpatialIndex } from "./spatial-index";

export interface StructuralBenchmarkResult { readonly nodeCount: number; readonly buildMs: number; readonly queryMs: number; readonly visibleCount: number }
export function syntheticDocument(nodeCount: number): DesignDocument {
  const nodes: Record<string, DesignNode> = { root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: [] } };
  const children: string[] = [];
  for (let i = 0; i < nodeCount; i++) { const id = `n${i}`; children.push(id); nodes[id] = { id, kind: i % 11 === 0 ? "TEXT" : i % 7 === 0 ? "IMAGE" : "SHAPE", parent_id: "root", children: [], transform: { x: (i % 100) * 80, y: Math.floor(i / 100) * 60, width: 64, height: 44 }, ...(i % 11 === 0 ? { content: `Label ${i}` } : {}), ...(i % 7 === 0 ? { asset_id: `asset-${i}` } : {}) }; }
  nodes.root = { ...nodes.root!, children };
  return { schema_version: "lumi.design-ir/1.0", document_id: `synthetic-${nodeCount}`, unit: "px", root_id: "root", nodes, resources: {}, metadata: { document_version: 0, applied_operation_ids: [] } };
}
export function runStructuralBenchmark(nodeCount: number): StructuralBenchmarkResult {
  const document = syntheticDocument(nodeCount); const start = performance.now(); const scene = buildScene(document); const buildMs = performance.now() - start;
  const index = new SpatialIndex(); index.rebuild(scene); const queryStart = performance.now(); const visible = index.query({ x: 0, y: 0, width: 1440, height: 900 }); const queryMs = performance.now() - queryStart;
  return { nodeCount, buildMs, queryMs, visibleCount: visible.length };
}
