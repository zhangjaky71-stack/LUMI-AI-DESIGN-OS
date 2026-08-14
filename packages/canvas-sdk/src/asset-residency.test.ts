import { describe, expect, it, vi } from "vitest";

import type { DesignDocument } from "../../design-ir/src/index";
import { CanvasAssetResidency } from "./asset-residency";
import { projectDesignDocument } from "./ir-scene";
import { CanvasResourceManager } from "./resource-manager";

function imageDocument(): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "asset-doc",
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
        transform: { x: 10, y: 10, width: 100, height: 100 },
      },
    },
    resources: {},
    metadata: { document_version: 1 },
  };
}

async function flushPromises(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

describe("CanvasResourceManager concurrency", () => {
  it("counts every waiter for a deduplicated in-flight texture load", async () => {
    const load = vi.fn(async (asset: { url: string }) => ({ texture: asset.url }));
    const manager = new CanvasResourceManager(
      {
        resolve: async (assetId, tier) => ({
          asset_id: assetId,
          tier,
          url: `memory://${assetId}/${tier}`,
          estimated_bytes: 1024,
        }),
      },
      { load, destroy: vi.fn() },
      4096,
    );
    const [first, second] = await Promise.all([
      manager.acquire("asset-a", "preview"),
      manager.acquire("asset-a", "preview"),
    ]);
    expect(first).toBe(second);
    expect(load).toHaveBeenCalledTimes(1);
    expect(manager.snapshot()[0]?.references).toBe(2);
    manager.release("asset-a", "preview");
    expect(manager.snapshot()[0]?.references).toBe(1);
  });
});

describe("CanvasAssetResidency", () => {
  it("loads visible assets progressively by zoom tier and invalidates the next frame", async () => {
    const resolvedTiers: string[] = [];
    const manager = new CanvasResourceManager(
      {
        resolve: async (assetId, tier) => {
          resolvedTiers.push(tier);
          return {
            asset_id: assetId,
            tier,
            url: `memory://${assetId}/${tier}`,
            estimated_bytes: 1024,
          };
        },
      },
      {
        load: async (asset) => ({ texture: asset.url }),
        destroy: vi.fn(),
      },
      8192,
    );
    const residency = new CanvasAssetResidency(manager);
    const invalidate = vi.fn();
    residency.setInvalidator(invalidate);
    const scene = projectDesignDocument(imageDocument());

    residency.update(scene, new Set(["image"]), 0.2);
    await flushPromises();
    expect(resolvedTiers).toEqual(["thumbnail"]);
    expect(residency.textureForAsset("asset-a")).toEqual({
      texture: "memory://asset-a/thumbnail",
    });
    expect(invalidate).toHaveBeenCalled();

    residency.update(scene, new Set(["image"]), 2);
    await flushPromises();
    expect(resolvedTiers).toEqual(["thumbnail", "full"]);
    expect(residency.textureForAsset("asset-a")).toEqual({
      texture: "memory://asset-a/full",
    });
    residency.destroy();
  });
});
