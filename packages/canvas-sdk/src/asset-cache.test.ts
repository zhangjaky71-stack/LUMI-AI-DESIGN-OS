import { describe, expect, it } from "vitest";

import { ProgressiveAssetCache } from "./asset-cache";

describe("progressive asset cache", () => {
  it("evicts least-recently-used unreferenced tiers", () => {
    let now = 0;
    const cache = new ProgressiveAssetCache(300, () => {
      now += 1;
      return now;
    });
    cache.put("asset-a", "thumbnail", 100);
    cache.put("asset-b", "thumbnail", 100);
    expect(cache.acquire("asset-a", "thumbnail")?.references).toBe(1);
    cache.put("asset-c", "preview", 180);

    const keys = cache.snapshot().map((entry) => entry.key);
    expect(keys).toContain("asset-a:thumbnail");
    expect(keys).not.toContain("asset-b:thumbnail");
    expect(keys).toContain("asset-c:preview");

    cache.release("asset-a", "thumbnail");
    cache.put("asset-d", "full", 240);
    expect(cache.totalBytes).toBeLessThanOrEqual(300);
  });

  it("keeps referenced entries even when the cache is temporarily over budget", () => {
    const cache = new ProgressiveAssetCache(100);
    cache.put("asset-a", "full", 80);
    cache.acquire("asset-a", "full");
    cache.put("asset-b", "full", 80);
    expect(cache.snapshot().map((entry) => entry.key)).toContain(
      "asset-a:full",
    );
  });
});
