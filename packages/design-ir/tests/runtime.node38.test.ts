import { describe, expect, it } from "vitest";
import fixtures from "../fixtures/conformance-v1.json";
import {
  CommandHistory,
  applyBatch,
  applyOperation,
  canonicalize,
  computeSemanticDiff,
  hashDocument,
  migrate,
  parseDocument,
  queryNodes,
  validateDocument,
  type DesignDocument,
  type DesignOperation,
} from "../src/index";

const base = fixtures.fixtures[0]!.document as unknown as DesignDocument;

describe("NODE-38 Design IR Runtime", () => {
  it("parses and validates the shared fixture", () => {
    expect(validateDocument(base)).toEqual([]);
    expect(parseDocument(base).document_id).toBe("poster-001");
  });

  it("matches every shared canonical/hash fixture", async () => {
    for (const fixture of fixtures.fixtures) {
      const doc = fixture.document as unknown as DesignDocument;
      expect(canonicalize(doc)).toBe(fixture.canonical);
      expect(await hashDocument(doc)).toBe(fixture.sha256);
    }
  });

  it("does not mutate the input document", () => {
    const before = structuredClone(base);
    const result = applyOperation(base, {
      operation_id: "set-text-1",
      type: "SET_TEXT",
      target_ids: ["headline"],
      expected_document_version: 7,
      payload: { content: "新的标题" },
    });
    expect(base).toEqual(before);
    expect(result.document.nodes.headline?.content).toBe("新的标题");
    expect(result.document_version).toBe(8);
  });

  it("rejects version conflicts", () => {
    expect(() =>
      applyOperation(base, {
        operation_id: "wrong-version",
        type: "SET_TEXT",
        target_ids: ["headline"],
        expected_document_version: 6,
        payload: { content: "x" },
      }),
    ).toThrowError(/IR_VERSION_CONFLICT/);
  });

  it("keeps batches atomic", () => {
    const operations: DesignOperation[] = [
      {
        operation_id: "move-1",
        type: "MOVE_NODE",
        target_ids: ["hero"],
        expected_document_version: 7,
        payload: { x: 100, y: 400 },
      },
      {
        operation_id: "bad-text",
        type: "SET_TEXT",
        target_ids: ["hero"],
        expected_document_version: 7,
        payload: { content: "not allowed" },
      },
    ];
    expect(() => applyBatch(base, operations, 7, "batch-atomic")).toThrowError(/IR_BATCH_FAILED/);
    expect(base.nodes.hero?.transform?.x).toBe(75.5);
  });

  it("runs constraint preflight before writes", () => {
    expect(() =>
      applyOperation(
        base,
        {
          operation_id: "constraint-fail",
          type: "MOVE_NODE",
          target_ids: ["hero"],
          expected_document_version: 7,
          payload: { x: -10, y: 1 },
        },
        (_document, operation) =>
          operation.payload.x === -10
            ? [{ code: "IR_CONSTRAINT_FAILED", message: "outside protected region" }]
            : [],
      ),
    ).toThrowError(/IR_CONSTRAINT_FAILED/);
  });

  it("queries semantic selectors without scanning in caller code", () => {
    expect(queryNodes(base, { role: "HEADLINE" }).map((node) => node.id)).toEqual(["headline"]);
    expect(queryNodes(base, { asset_binding: "asset:coffee-001" }).map((node) => node.id)).toEqual([
      "hero",
    ]);
    expect(queryNodes(base, { frame_id: "frame" }).map((node) => node.id).sort()).toEqual([
      "frame",
      "headline",
      "hero",
    ]);
  });

  it("produces a machine-readable semantic diff", () => {
    const result = applyOperation(base, {
      operation_id: "asset-1",
      type: "REPLACE_ASSET",
      target_ids: ["hero"],
      expected_document_version: 7,
      payload: { asset_id: "asset:coffee-002" },
    });
    expect(result.diff.asset_replaced).toEqual(["hero"]);
    expect(result.diff.nodes_added).toEqual([]);
    expect(computeSemanticDiff(base, result.document).asset_replaced).toEqual(["hero"]);
  });

  it("migrates through the declared chain and preserves provenance", () => {
    const migrated = migrate(base, "2.0");
    expect(migrated.schema_version).toBe("2.0");
    const provenance = migrated.metadata.migration_provenance;
    expect(Array.isArray(provenance)).toBe(true);
    expect((provenance as unknown[]).length).toBe(2);
  });

  it("supports command undo/redo snapshots", () => {
    const execution = applyOperation(base, {
      operation_id: "history-text",
      type: "SET_TEXT",
      target_ids: ["headline"],
      expected_document_version: 7,
      payload: { content: "history" },
    });
    const history = new CommandHistory();
    history.push(base, execution);
    expect(history.undo(execution.document).nodes.headline?.content).toBe("Café 新品");
    expect(history.redo(base).nodes.headline?.content).toBe("history");
  });

  it("rejects non-finite values", () => {
    const invalid = structuredClone(base) as DesignDocument;
    const hero = invalid.nodes.hero!;
    (hero.transform as { x?: number }).x = Number.NaN;
    expect(validateDocument(invalid)[0]?.code).toBe("IR_SCHEMA_INVALID");
  });

  it("prevents graph cycles during reparent", () => {
    expect(() =>
      applyOperation(base, {
        operation_id: "cycle",
        type: "REPARENT_NODE",
        target_ids: ["frame"],
        expected_document_version: 7,
        payload: { parent_id: "headline" },
      }),
    ).toThrowError(/IR_GRAPH_CYCLE/);
  });

  it("keeps deterministic reorder invariants across randomized commands", () => {
    let doc = structuredClone(base);
    for (let index = 0; index < 40; index += 1) {
      const version = Number(doc.metadata.document_version);
      const operation: DesignOperation = {
        operation_id: `reorder-${index}`,
        type: "REORDER_NODE",
        target_ids: [index % 2 === 0 ? "headline" : "hero"],
        expected_document_version: version,
        payload: { index: index % 3 },
      };
      doc = applyOperation(doc, operation).document;
      expect(validateDocument(doc)).toEqual([]);
    }
  });
});

describe("NODE-38 reference benchmark", () => {
  it("records a 2k-node parse and 100-op batch", () => {
    const nodes: Record<string, any> = {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
      frame: {
        id: "frame",
        kind: "FRAME",
        parent_id: "root",
        children: Array.from({ length: 2000 }, (_, i) => `n${i}`),
      },
    };
    for (let i = 0; i < 2000; i += 1) {
      nodes[`n${i}`] = {
        id: `n${i}`,
        kind: "TEXT",
        parent_id: "frame",
        children: [],
        content: `node-${i}`,
        transform: { x: i % 100, y: Math.floor(i / 100), width: 20, height: 10 },
      };
    }
    const document: DesignDocument = {
      schema_version: "1.0",
      document_id: "benchmark-2k",
      unit: "px",
      root_id: "root",
      nodes,
      resources: {},
      metadata: { document_version: 0 },
    };
    const started = performance.now();
    parseDocument(document);
    const parseMs = performance.now() - started;
    const operations: DesignOperation[] = Array.from({ length: 100 }, (_, i) => ({
      operation_id: `bench-${i}`,
      type: "MOVE_NODE",
      target_ids: [`n${i}`],
      expected_document_version: 0,
      payload: { x: i, y: i + 1 },
    }));
    const batchStart = performance.now();
    const result = applyBatch(document, operations, 0, "benchmark-batch");
    const batchMs = performance.now() - batchStart;
    expect(result.document_version).toBe(1);
    expect(parseMs).toBeLessThan(5000);
    expect(batchMs).toBeLessThan(5000);
    console.info(`NODE38_BENCH parse_2k_ms=${parseMs.toFixed(3)} batch_100_ms=${batchMs.toFixed(3)}`);
  });
});
