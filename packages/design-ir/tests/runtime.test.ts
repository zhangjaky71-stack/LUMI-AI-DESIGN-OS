import { describe, expect, it } from "vitest";
import fixture from "../../../fixtures/design-ir/node-38-conformance.json";
import {
  DesignIrMigrationRegistry,
  canonicalSha256,
  canonicalStringify,
  executeOperations,
  semanticDiff,
  type DesignDocument,
  type DesignOperation,
} from "../src";

const source = fixture.document as DesignDocument;
const operations = fixture.operations as DesignOperation[];

describe("NODE-38 Design IR runtime", () => {
  it("matches the frozen cross-runtime canonical vectors", async () => {
    expect(await canonicalSha256(source)).toBe(fixture.expected_input_sha256);
    const result = executeOperations(source, operations);
    expect(result.ok).toBe(true);
    expect(await canonicalSha256(result.document)).toBe(fixture.expected_output_sha256);
  });

  it("does not mutate the caller document", () => {
    const before = canonicalStringify(source);
    const result = executeOperations(source, operations);
    expect(result.ok).toBe(true);
    expect(canonicalStringify(source)).toBe(before);
    expect(result.document).not.toBe(source);
  });

  it("rolls back the whole transaction if any operation fails", () => {
    const failing: DesignOperation[] = [
      operations[0]!,
      {
        operation_id: "missing-target",
        type: "SET_TEXT",
        target_ids: ["does-not-exist"],
        expected_document_version: 7,
        payload: { content: "must roll back" },
      },
    ];
    const result = executeOperations(source, failing);
    expect(result.ok).toBe(false);
    expect(result.document).toBe(source);
    expect(canonicalStringify(result.document)).toBe(canonicalStringify(source));
    if (!result.ok) expect(result.failures[0]?.code).toBe("TARGET_NOT_FOUND");
  });

  it("fails closed on optimistic concurrency mismatch", () => {
    const result = executeOperations(source, [
      { ...operations[0]!, expected_document_version: 6 },
    ]);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.failures[0]?.code).toBe("VERSION_CONFLICT");
  });

  it("is deterministic across repeated equivalent transactions", () => {
    const hashes = new Set<string>();
    for (let index = 0; index < 50; index += 1) {
      const result = executeOperations(structuredClone(source), structuredClone(operations));
      expect(result.ok).toBe(true);
      hashes.add(canonicalStringify(result.document));
    }
    expect(hashes.size).toBe(1);
  });

  it("emits semantic rather than raw JSON diff categories", () => {
    const result = executeOperations(source, operations);
    expect(result.ok).toBe(true);
    const diff = semanticDiff(source, result.document);
    expect(diff.changed_node_ids).toContain("headline");
    expect(diff.changes.some((change) => change.kind === "TEXT_CHANGED")).toBe(true);
    expect(diff.changes.some((change) => change.kind === "GEOMETRY_CHANGED")).toBe(true);
  });

  it("preserves provenance during registered migrations", () => {
    const registry = new DesignIrMigrationRegistry();
    registry.register({
      from: "1.0",
      to: "1.1",
      migrate: (document) => ({
        ...document,
        schema_version: "1.1",
        metadata: { document_version: document.metadata.document_version ?? 0 },
      }),
    });
    const migrated = registry.migrate(source, "1.1");
    expect(migrated.schema_version).toBe("1.1");
    expect(migrated.metadata.provenance).toEqual(source.metadata.provenance);
    expect(source.schema_version).toBe("1.0");
  });
});
