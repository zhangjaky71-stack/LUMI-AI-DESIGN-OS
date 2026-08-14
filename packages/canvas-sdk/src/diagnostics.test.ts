import { describe, expect, it } from "vitest";

import type { DesignDocument } from "../../design-ir/src/index";
import { projectDesignDocument } from "./ir-scene";

function malformed(): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "malformed-doc",
    unit: "px",
    root_id: "root",
    nodes: {
      root: {
        id: "root",
        kind: "DOCUMENT_ROOT",
        parent_id: null,
        children: ["frame", "missing-child"],
      },
      frame: {
        id: "frame",
        kind: "FRAME",
        parent_id: "wrong-parent",
        children: [],
        transform: { x: 10, y: 10, width: 100, height: 100 },
      },
      orphan: {
        id: "orphan",
        kind: "custom:future-widget",
        parent_id: "ghost",
        children: [],
        transform: { x: 300, y: 200, width: 50, height: 50 },
      },
    },
    resources: {},
    metadata: { document_version: 1 },
  };
}

describe("Canvas scene diagnostics", () => {
  it("isolates malformed nodes without crashing the entire canvas projection", () => {
    const scene = projectDesignDocument(malformed());
    expect(scene.nodes.has("frame")).toBe(true);
    expect(scene.nodes.has("orphan")).toBe(true);
    expect(scene.diagnostics.some((item) => item.code === "MISSING_CHILD")).toBe(true);
    expect(scene.diagnostics.some((item) => item.code === "MISSING_PARENT")).toBe(true);
    expect(scene.diagnostics.some((item) => item.code === "UNSUPPORTED_KIND")).toBe(true);
  });
});
