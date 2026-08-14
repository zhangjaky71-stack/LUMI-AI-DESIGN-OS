import { ProgressiveAssetCache, type AssetTier } from "./asset-cache";

export interface ResolvedCanvasAsset {
  readonly asset_id: string;
  readonly tier: AssetTier;
  readonly url: string;
  readonly estimated_bytes: number;
  readonly expires_at?: string;
}

export interface CanvasAssetResolver {
  resolve(assetId: string, tier: AssetTier): Promise<ResolvedCanvasAsset>;
}

export interface CanvasResourceLoader<T> {
  load(asset: ResolvedCanvasAsset): Promise<T>;
  destroy(resource: T): void;
}

interface ResourceEntry<T> {
  readonly key: string;
  readonly assetId: string;
  readonly tier: AssetTier;
  readonly resource: T;
  references: number;
}

function resourceKey(assetId: string, tier: AssetTier): string {
  return `${assetId}:${tier}`;
}

export class CanvasResourceManager<T> {
  readonly #resolver: CanvasAssetResolver;
  readonly #loader: CanvasResourceLoader<T>;
  readonly #cache: ProgressiveAssetCache;
  readonly #resources = new Map<string, ResourceEntry<T>>();
  readonly #inflight = new Map<string, Promise<ResourceEntry<T>>>();

  constructor(
    resolver: CanvasAssetResolver,
    loader: CanvasResourceLoader<T>,
    budgetBytes = 256 * 1024 * 1024,
  ) {
    this.#resolver = resolver;
    this.#loader = loader;
    this.#cache = new ProgressiveAssetCache(budgetBytes);
  }

  async acquire(assetId: string, tier: AssetTier): Promise<T> {
    const key = resourceKey(assetId, tier);
    const existing = this.#resources.get(key);
    if (existing) {
      existing.references += 1;
      this.#cache.acquire(assetId, tier);
      return existing.resource;
    }

    const pending = this.#inflight.get(key) ?? this.#load(assetId, tier);
    this.#inflight.set(key, pending);
    try {
      const entry = await pending;
      entry.references += 1;
      this.#cache.acquire(assetId, tier);
      return entry.resource;
    } finally {
      this.#inflight.delete(key);
    }
  }

  release(assetId: string, tier: AssetTier): void {
    const key = resourceKey(assetId, tier);
    const entry = this.#resources.get(key);
    if (!entry) return;
    entry.references = Math.max(0, entry.references - 1);
    this.#cache.release(assetId, tier);
    this.#collectEvicted();
  }

  releaseAsset(assetId: string): void {
    for (const entry of this.#resources.values()) {
      if (entry.assetId === assetId) entry.references = 0;
    }
    this.#cache.remove(assetId);
    for (const [key, entry] of this.#resources) {
      if (entry.assetId !== assetId) continue;
      this.#loader.destroy(entry.resource);
      this.#resources.delete(key);
    }
  }

  disposeUnused(): number {
    let disposed = 0;
    for (const [key, entry] of this.#resources) {
      if (entry.references > 0) continue;
      this.#loader.destroy(entry.resource);
      this.#resources.delete(key);
      this.#cache.remove(entry.assetId, entry.tier);
      disposed += 1;
    }
    return disposed;
  }

  destroy(): void {
    for (const entry of this.#resources.values()) this.#loader.destroy(entry.resource);
    this.#resources.clear();
    this.#inflight.clear();
  }

  snapshot(): ReadonlyArray<{ readonly asset_id: string; readonly tier: AssetTier; readonly references: number }> {
    return [...this.#resources.values()]
      .map((entry) => ({ asset_id: entry.assetId, tier: entry.tier, references: entry.references }))
      .sort((left, right) => `${left.asset_id}:${left.tier}`.localeCompare(`${right.asset_id}:${right.tier}`));
  }

  async #load(assetId: string, tier: AssetTier): Promise<ResourceEntry<T>> {
    const resolved = await this.#resolver.resolve(assetId, tier);
    if (resolved.asset_id !== assetId || resolved.tier !== tier) {
      throw new Error("asset resolver returned mismatched identity or tier");
    }
    const resource = await this.#loader.load(resolved);
    const entry: ResourceEntry<T> = {
      key: resourceKey(assetId, tier),
      assetId,
      tier,
      resource,
      references: 0,
    };
    this.#resources.set(entry.key, entry);
    this.#cache.put(assetId, tier, Math.max(1, resolved.estimated_bytes));
    this.#collectEvicted();
    return entry;
  }

  #collectEvicted(): void {
    const liveCacheKeys = new Set(this.#cache.snapshot().map((entry) => entry.key));
    for (const [key, entry] of this.#resources) {
      if (liveCacheKeys.has(key) || entry.references > 0) continue;
      this.#loader.destroy(entry.resource);
      this.#resources.delete(key);
    }
  }
}
