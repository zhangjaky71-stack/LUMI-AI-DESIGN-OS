import { describe, expect, it } from "vitest";

import { parseCanvasProjection, wireDescriptor } from "./types";

describe("NODE-55 Canvas projection contract", () => {
  it("normalizes Python Design IR schema and page parent only in the browser projection", () => {
    const projection = parseCanvasProjection({
      design_document_id: "0198a100-0000-7000-8000-000000000001",
      design_document_version_id: "0198a100-0000-7000-8000-000000000002",
      version_number: 3,
      revision: 7,
      content_hash: "a".repeat(64),
      active_page_id: "0198a100-0000-7000-8000-000000000003",
      document: {
        schema_version: "lumi.design-ir/1.0",
        document_id: "0198a100-0000-7000-8000-000000000001",
        unit: "px",
        root_id: "document-root:0198a100-0000-7000-8000-000000000001",
        nodes: {
          "document-root:0198a100-0000-7000-8000-000000000001": {
            id: "document-root:0198a100-0000-7000-8000-000000000001",
            kind: "DOCUMENT_ROOT",
            parent_id: null,
            children: ["0198a100-0000-7000-8000-000000000003"],
          },
          "0198a100-0000-7000-8000-000000000003": {
            id: "0198a100-0000-7000-8000-000000000003",
            kind: "GROUP",
            parent_id: null,
            children: [],
            metadata: { source_kind: "page" },
          },
        },
        resources: {},
        metadata: { document_version: 7 },
      },
    });

    expect(projection.document.schema_version).toBe("1.0");
    expect(
      projection.document.nodes["0198a100-0000-7000-8000-000000000003"]?.parent_id,
    ).toBe("document-root:0198a100-0000-7000-8000-000000000001");
    expect(projection.revision).toBe(7);
  });

  it("compiles SDK CREATE_NODE and SET_PROPERTY descriptors to the safe wire", () => {
    expect(
      wireDescriptor({
        type: "CREATE_NODE",
        targetIds: [],
        payload: {
          node: {
            id: "0198a100-0000-7000-8000-000000000010",
            kind: "FRAME",
            parent_id: "0198a100-0000-7000-8000-000000000003",
            name: "9:16 Frame",
            children: [],
            transform: { x: 10, y: 20, width: 1080, height: 1920 },
          },
        },
      }),
    ).toMatchObject({
      type: "CREATE_NODE",
      target_ids: [],
      payload: {
        kind: "FRAME",
        id: "0198a100-0000-7000-8000-000000000010",
        parent_id: "0198a100-0000-7000-8000-000000000003",
        x: 10,
        y: 20,
        width: 1080,
        height: 1920,
      },
    });

    expect(
      wireDescriptor({
        type: "SET_PROPERTY",
        targetIds: ["node-1"],
        payload: { property: "locked", value: true },
      }),
    ).toEqual({
      type: "SET_PROPERTY",
      target_ids: ["node-1"],
      payload: { path: "locked", value: true },
    });
  });

  it("maps text content and subtree delete to server semantics", () => {
    expect(
      wireDescriptor({
        type: "SET_TEXT",
        targetIds: ["text-1"],
        payload: { content: "Updated headline" },
      }),
    ).toEqual({
      type: "SET_TEXT",
      target_ids: ["text-1"],
      payload: { text: "Updated headline" },
    });

    expect(
      wireDescriptor({
        type: "DELETE_NODE",
        targetIds: ["frame-1"],
        payload: {},
      }),
    ).toMatchObject({ payload: { recursive: true } });
  });
});
