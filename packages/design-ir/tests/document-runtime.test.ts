import { describe, expect, it } from "vitest";
import fixture from "../../../fixtures/design-ir/node-38-conformance.json";
import {
  DesignIrHistory,
  hashDocument,
  parseDocument,
  queryNodes,
  validateDocument,
  type DesignDocument,
  type DesignOperation,
} from "../src";

const source = fixture.document as DesignDocument;

describe("NODE-38 document runtime", () => {
  it("parses a structurally valid V1 document", () => {
    const parsed = parseDocument(source);
    expect(validateDocument(parsed)).toEqual({ valid: true, issues: [] });
    expect(parsed).not.toBe(source);
  });

  it("detects graph cycles and missing references", () => {
    const cyclic = structuredClone(source) as DesignDocument;
    const raw = cyclic as unknown as {
      nodes: Record<string, { parent_id: string | null; children: string[] }>;
    };
    raw.nodes.root!.parent_id = "headline";
    raw.nodes.headline!.children.push("root");
    const result = validateDocument(cyclic);
    expect(result.valid).toBe(false);
    expect(result.issues.some((value) => value.code === "IR_GRAPH_CYCLE")).toBe(true);
  });

  it("queries local semantic slices without scanning in callers", () => {
    expect(queryNodes(source, { kinds: ["TEXT"], parent_id: "root" }).map((node) => node.id)).toEqual([
      "headline",
    ]);
  });

  it("normalizes Unicode and excludes ephemeral metadata from document hashes", async () => {
    const left = structuredClone(source) as DesignDocument;
    const right = structuredClone(source) as DesignDocument;
    const leftRaw = left as unknown as { metadata: Record<string, unknown>; nodes: Record<string, Record<string, unknown>> };
    const rightRaw = right as unknown as { metadata: Record<string, unknown>; nodes: Record<string, Record<string, unknown>> };
    leftRaw.metadata.viewport = { x: 1, y: 2 };
    rightRaw.metadata.viewport = { x: 999, y: 999 };
    leftRaw.nodes.headline!.content = "Cafe\u0301";
    rightRaw.nodes.headline!.content = "Café";
    expect(await hashDocument(left)).toBe(await hashDocument(right));
  });

  it("records deterministic undo and redo snapshots", () => {
    const history = new DesignIrHistory();
    const operation = fixture.operations[0] as DesignOperation;
    const result = history.apply(source, [operation]);
    expect(result.ok).toBe(true);
    expect(history.canUndo()).toBe(true);
    expect(history.undo()?.nodes.headline?.content).toBe("Hello");
    expect(history.canRedo()).toBe(true);
    expect(history.redo()?.nodes.headline?.content).toBe("你好 LUMI");
  });
});
