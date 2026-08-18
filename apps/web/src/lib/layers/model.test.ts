import { describe, expect, it } from "vitest";
import type { DesignDocument, DesignNode } from "@lumi/design-ir";

import {
  commonValue,
  constraintBadges,
  flattenLayerRows,
  virtualLayerWindow,
} from "./model";

function documentWith(count: number): DesignDocument {
  const children = Array.from({ length: count }, (_, index) => `node-${index}`);
  const nodes: Record<string, DesignNode> = {
    root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children },
  };
  for (let index = 0; index < count; index += 1) {
    nodes[`node-${index}`] = {
      id: `node-${index}`,
      kind: index % 5 === 0 ? "TEXT" : "SHAPE",
      name: index === count - 1 ? "Needle headline" : `Layer ${index}`,
      parent_id: "root",
      children: [],
      locked: index === 7,
      opacity: index % 2 ? 1 : 0.5,
      transform: { x: index, y: index, width: 100, height: 100 },
      semantic: { tags: index === count - 1 ? ["headline"] : [] },
    };
  }
  return { schema_version: "1.0", document_id: "doc", unit: "px", root_id: "root", nodes, resources: {}, metadata: { document_version: 1 } };
}

describe("NODE-56 layer model", () => {
  it("virtualizes a 10k layer tree instead of returning 10k rendered rows", () => {
    const rows = flattenLayerRows(documentWith(10_000), new Set());
    expect(rows).toHaveLength(10_000);
    const windowed = virtualLayerWindow(rows, 90_000, 600);
    expect(windowed.rows.length).toBeLessThanOrEqual(40);
    expect(windowed.totalHeight).toBe(300_000);
    expect(windowed.start).toBeGreaterThan(2_900);
  });

  it("searches name/role/kind/tag while retaining only relevant rows", () => {
    const rows = flattenLayerRows(documentWith(100), new Set(), "headline");
    expect(rows).toHaveLength(1);
    expect(rows[0]?.id).toBe("node-99");
    expect(rows[0]?.matched).toBe(true);
  });

  it("reports mixed multi-select values without inventing a common value", () => {
    const document = documentWith(3);
    const nodes = [document.nodes["node-0"]!, document.nodes["node-1"]!];
    const opacity = commonValue(nodes, (node) => node.opacity);
    expect(opacity.mixed).toBe(true);
    expect(opacity.value).toBeUndefined();
  });

  it("labels persisted locks honestly when source metadata is unavailable", () => {
    const document = documentWith(10);
    const badges = constraintBadges(document.nodes["node-7"]!);
    expect(badges[0]?.severity).toBe("HARD");
    expect(badges[0]?.source).toBe("UNRESOLVED");
  });
});