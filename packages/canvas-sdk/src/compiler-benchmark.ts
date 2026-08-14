import {
  executeOperations,
  getDocumentVersion,
  type DesignDocument,
  type DesignOperation,
  type DesignNode,
} from "../../design-ir/src/index";
import { CanvasCompiler } from "./compiler";

export interface CanvasCompilerBenchmarkResult {
  readonly node_count: number;
  readonly operation_count: number;
  readonly full_compile_ms: number;
  readonly incremental_compile_ms: number;
  readonly dirty_node_count: number;
  readonly upserted_node_count: number;
  readonly fallback_to_full: boolean;
  readonly equivalent_compile_hash: boolean;
}

export function createCompilerBenchmarkDocument(nodeCount = 2_000): DesignDocument {
  if (!Number.isInteger(nodeCount) || nodeCount < 2) {
    throw new Error("nodeCount must be an integer >= 2");
  }
  const nodes: Record<string, DesignNode> = {
    root: {
      id: "root",
      kind: "DOCUMENT_ROOT",
      parent_id: null,
      children: ["frame"],
    },
    frame: {
      id: "frame",
      kind: "FRAME",
      parent_id: "root",
      children: [],
      transform: { x: 0, y: 0, width: 4_000, height: 4_000 },
    },
  };
  const children: string[] = [];
  for (let index = 0; index < nodeCount - 2; index += 1) {
    const id = `node-${index}`;
    children.push(id);
    const column = index % 50;
    const row = Math.floor(index / 50);
    nodes[id] = {
      id,
      kind: index % 10 === 0 ? "TEXT" : "SHAPE",
      parent_id: "frame",
      children: [],
      ...(index % 10 === 0 ? { content: `Node ${index}` } : {}),
      transform: {
        x: column * 72,
        y: row * 72,
        width: 64,
        height: 64,
      },
    };
  }
  nodes.frame = { ...nodes.frame!, children };
  return {
    schema_version: "1.0",
    document_id: `compiler-benchmark-${nodeCount}`,
    unit: "px",
    root_id: "root",
    nodes,
    resources: {},
    metadata: { document_version: 1 },
  };
}

function moveOperations(document: DesignDocument, operationCount: number): DesignOperation[] {
  const version = getDocumentVersion(document);
  return Array.from({ length: operationCount }, (_, index) => ({
    operation_id: `benchmark-move-${index}`,
    type: "MOVE_NODE" as const,
    target_ids: [`node-${index}`],
    expected_document_version: version,
    payload: { dx: 3, dy: -2 },
    reason: "canvas-compiler-benchmark",
  }));
}

export async function runCanvasCompilerBenchmark(
  nodeCount = 2_000,
  operationCount = 100,
  now: () => number = () => performance.now(),
): Promise<CanvasCompilerBenchmarkResult> {
  const before = createCompilerBenchmarkDocument(nodeCount);
  const compiler = new CanvasCompiler();
  const initial = await compiler.fullCompile(before);
  if (!initial.ok) throw new Error("initial compiler benchmark document failed to compile");

  const execution = executeOperations(before, moveOperations(before, operationCount));
  if (!execution.ok) throw new Error("compiler benchmark operations failed");
  const after = execution.document;

  const fullStart = now();
  const full = await compiler.fullCompile(after);
  const fullEnd = now();
  if (!full.ok) throw new Error("full compiler benchmark failed");

  const incrementalStart = now();
  const incremental = await compiler.incrementalCompile({
    previous: initial.snapshot,
    before,
    after,
  });
  const incrementalEnd = now();
  if (!incremental.ok || !("patch" in incremental)) {
    throw new Error("incremental compiler benchmark failed");
  }

  return {
    node_count: nodeCount,
    operation_count: operationCount,
    full_compile_ms: Math.max(0, fullEnd - fullStart),
    incremental_compile_ms: Math.max(0, incrementalEnd - incrementalStart),
    dirty_node_count: incremental.dirty_node_ids.length,
    upserted_node_count: incremental.patch.upserted_nodes.length,
    fallback_to_full: incremental.fallback_to_full,
    equivalent_compile_hash:
      incremental.snapshot.provenance.compile_hash === full.snapshot.provenance.compile_hash,
  };
}
