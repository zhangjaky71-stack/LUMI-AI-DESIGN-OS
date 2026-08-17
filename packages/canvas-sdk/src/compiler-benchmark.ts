import type { DesignDocument, DesignNode } from "../../design-ir/src/index";
import { CanvasCompiler } from "./compiler";

export function makeCompilerBenchmarkDocument(nodeCount: number): DesignDocument {
  const rootChildren: string[] = [];
  const nodes: Record<string, DesignNode> = {
    root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: rootChildren },
  };
  for (let index = 0; index < nodeCount; index += 1) {
    const id = `shape-${index}`;
    rootChildren.push(id);
    nodes[id] = {
      id,
      kind: index % 7 === 0 ? "TEXT" : "SHAPE",
      parent_id: "root",
      children: [],
      transform: { x: (index % 100) * 24, y: Math.floor(index / 100) * 24, width: 20, height: 20 },
      ...(index % 7 === 0 ? { content: `Label ${index}` } : {}),
    };
  }
  return { schema_version: "2.0", document_id: `bench-${nodeCount}`, unit: "px", root_id: "root", nodes, resources: {}, metadata: {} };
}

export async function benchmarkCompiler(nodeCount: number): Promise<{ readonly nodeCount: number; readonly fullMs: number }> {
  const document = makeCompilerBenchmarkDocument(nodeCount);
  const compiler = new CanvasCompiler();
  const start = performance.now();
  const result = await compiler.compileFull(document);
  if (!result.ok) throw new Error("COMPILER_BENCHMARK_FAILED");
  return { nodeCount, fullMs: performance.now() - start };
}
