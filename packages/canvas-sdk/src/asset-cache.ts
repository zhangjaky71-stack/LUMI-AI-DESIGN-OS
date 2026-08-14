export type AssetTier = "thumbnail" | "preview" | "full";

export interface AssetCacheEntry {
  readonly key: string;
  readonly assetId: string;
  readonly tier: AssetTier;
  readonly bytes: number;
  readonly references: number;
  readonly lastAccess: number;
}

interface MutableAssetCacheEntry {
  key: string;
  assetId: string;
  tier: AssetTier;
  bytes: number;
  references: number;
  lastAccess: number;
}

export class ProgressiveAssetCache {
  readonly #entries = new Map<string, MutableAssetCacheEntry>();
  readonly #budgetBytes: number;
  readonly #now: () => number;

  constructor(budgetBytes: number, now: () => number = () => Date.now()) {
    if (budgetBytes <= 0) {
      throw new Error("asset cache budget must be positive");
    }
    this.#budgetBytes = budgetBytes;
    this.#now = now;
  }

  put(assetId: string, tier: AssetTier, bytes: number, initialReferences?: number): AssetCacheEntry {
    if (bytes <= 0) {
      throw new Error("asset cache entry bytes must be positive");
    }
    const key = `${assetId}:${tier}`;
    const existing = this.#entries.get(key);
    const entry: MutableAssetCacheEntry = {
      key,
      assetId,
      tier,
      bytes,
      references: Math.max(0, initialReferences ?? existing?.references ?? 0),
      lastAccess: this.#now(),
    };
    this.#entries.set(key, entry);
    this.evict();
    return { ...entry };
  }

  acquire(assetId: string, tier: AssetTier): AssetCacheEntry | null {
    const entry = this.#entries.get(`${assetId}:${tier}`);
    if (!entry) {
      return null;
    }
    entry.references += 1;
    entry.lastAccess = this.#now();
    return { ...entry };
  }

  release(assetId: string, tier: AssetTier): void {
    const entry = this.#entries.get(`${assetId}:${tier}`);
    if (!entry) {
      return;
    }
    entry.references = Math.max(0, entry.references - 1);
    entry.lastAccess = this.#now();
    this.evict();
  }

  remove(assetId: string, tier?: AssetTier): string[] {
    const removed: string[] = [];
    for (const [key, entry] of this.#entries) {
      if (entry.assetId === assetId && (tier === undefined || entry.tier === tier)) {
        this.#entries.delete(key);
        removed.push(key);
      }
    }
    return removed;
  }

  evict(): string[] {
    const evicted: string[] = [];
    while (this.totalBytes > this.#budgetBytes) {
      const candidate = [...this.#entries.values()]
        .filter((entry) => entry.references === 0)
        .sort((a, b) => a.lastAccess - b.lastAccess || a.key.localeCompare(b.key))[0];
      if (!candidate) break;
      this.#entries.delete(candidate.key);
      evicted.push(candidate.key);
    }
    return evicted;
  }

  snapshot(): AssetCacheEntry[] {
    return [...this.#entries.values()]
      .map((entry) => ({ ...entry }))
      .sort((a, b) => a.key.localeCompare(b.key));
  }

  get totalBytes(): number {
    let total = 0;
    for (const entry of this.#entries.values()) total += entry.bytes;
    return total;
  }
}
