import { describe, expect, it, vi } from "vitest";

import type { DesignDocument } from "../../design-ir/src/index";
import { buildPasteOperations, createClipboardFragment } from "./clipboard";
import { CanvasResourceManager } from "./resource-manager";
import { CanvasTextEditSession, graphemeCount } from "./text-edit";

function documentFixture(): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "source-doc",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["image"] },
      image: {
        id: "image",
        kind: "IMAGE",
        parent_id: "root",
        children: [],
        asset_id: "asset-a",
        transform: { x: 10, y: 20, width: 100, height: 80 },
        metadata: { "runtime:pixi-handle": "must-not-copy", note: "keep" },
      },
    },
    resources: {},
    metadata: { document_version: 1 },
  };
}

describe("Canvas text editing", () => {
  it("does not commit incomplete Chinese IME composition", () => {
    const session = new CanvasTextEditSession("text", "初始");
    session.compositionStart();
    session.input("初始设");
    expect(session.commitOperation(documentFixture(), "text-op")).toBeNull();
    session.compositionEnd("初始设计");
    const operation = session.commitOperation(documentFixture(), "text-op");
    expect(operation?.type).toBe("SET_TEXT");
    expect(operation?.payload.content).toBe("初始设计");
  });

  it("counts emoji families as graphemes when Intl.Segmenter is available", () => {
    expect(graphemeCount("你👨‍👩‍👧‍👦")).toBe(2);
  });
});

describe("Canvas asset resource lifecycle", () => {
  it("deduplicates loads and destroys unused GPU resources", async () => {
    const destroy = vi.fn();
    const manager = new CanvasResourceManager(
      {
        resolve: async (assetId, tier) => ({
          asset_id: assetId,
          tier,
          url: `memory://${assetId}/${tier}`,
          estimated_bytes: 1024,
        }),
      },
      {
        load: async (asset) => ({ key: asset.url }),
        destroy,
      },
      4096,
    );
    const first = await manager.acquire("asset-a", "preview");
    const second = await manager.acquire("asset-a", "preview");
    expect(first).toBe(second);
    expect(manager.snapshot()[0]?.references).toBe(2);
    manager.release("asset-a", "preview");
    manager.release("asset-a", "preview");
    expect(manager.disposeUnused()).toBe(1);
    expect(destroy).toHaveBeenCalledTimes(1);
  });
});

describe("Design IR clipboard", () => {
  it("sanitizes runtime metadata and revalidates assets across documents", () => {
    const source = documentFixture();
    const fragment = createClipboardFragment(source, ["image"]);
    expect(fragment.nodes.image?.metadata?.["runtime:pixi-handle"]).toBeUndefined();
    const target: DesignDocument = {
      ...source,
      document_id: "target-doc",
      nodes: { root: source.nodes.root! },
      metadata: { document_version: 7 },
    };
    const operations = buildPasteOperations(
      fragment,
      target,
      "root",
      "paste",
      { mapAssetId: (assetId) => `copied-${assetId}` },
    );
    expect(operations).toHaveLength(1);
    const pasted = operations[0]?.payload.node as Record<string, unknown>;
    expect(pasted.asset_id).toBe("copied-asset-a");
    expect((pasted.transform as { x: number }).x).toBe(34);
  });
});
