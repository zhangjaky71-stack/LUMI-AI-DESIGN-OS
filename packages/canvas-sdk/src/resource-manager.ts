import type { AssetResolver, AssetTier, TextureHandle, TextureLoader } from "./types";

interface CacheEntry { readonly assetId: string; tier: AssetTier; handle: TextureHandle; refCount: number; lastUsed: number }
function key(assetId: string, tier: AssetTier): string { return `${assetId}:${tier}`; }

export class CanvasResourceManager {
  private readonly cache = new Map<string, CacheEntry>();
  private clock = 0;
  constructor(private readonly resolver: AssetResolver, private readonly loader: TextureLoader, private readonly maxEntries = 128) {}
  async acquire(assetId: string, tier: AssetTier = "preview"): Promise<TextureHandle> {
    const cacheKey = key(assetId, tier); const existing = this.cache.get(cacheKey);
    if (existing) { existing.refCount += 1; existing.lastUsed = ++this.clock; return existing.handle; }
    const source = await this.resolver.resolve(assetId, tier);
    if (source.assetId !== assetId || source.tier !== tier || !/^https?:\/\//.test(source.url)) throw new Error("CANVAS_ASSET_RESOLUTION_INVALID");
    const handle = await this.loader.load(source);
    this.cache.set(cacheKey, { assetId, tier, handle, refCount: 1, lastUsed: ++this.clock });
    this.evict(); return handle;
  }
  release(assetId: string, tier: AssetTier = "preview"): void { const entry = this.cache.get(key(assetId, tier)); if (!entry) return; entry.refCount = Math.max(0, entry.refCount - 1); entry.lastUsed = ++this.clock; this.evict(); }
  async promote(assetId: string): Promise<TextureHandle> { return this.acquire(assetId, "full"); }
  releaseNodeAssets(assetIds: readonly string[]): void { for (const assetId of assetIds) { this.release(assetId, "preview"); this.release(assetId, "full"); } }
  evict(force = false): void {
    const candidates = [...this.cache.entries()].filter(([, entry]) => entry.refCount === 0).sort((a, b) => a[1].lastUsed - b[1].lastUsed);
    while (candidates.length && (force || this.cache.size > this.maxEntries)) { const [cacheKey, entry] = candidates.shift()!; entry.handle.destroy(); this.cache.delete(cacheKey); }
  }
  destroy(): void { for (const entry of this.cache.values()) entry.handle.destroy(); this.cache.clear(); }
  get size(): number { return this.cache.size; }
}
