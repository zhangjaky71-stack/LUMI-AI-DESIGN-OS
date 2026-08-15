export type QueryKeyPart = string | number | boolean | null;

interface CacheEntry<T> {
  readonly value: T;
  readonly expires_at: number;
}

export class OrgScopedQueryCache {
  #organizationId: string;
  readonly #cache = new Map<string, CacheEntry<unknown>>();
  readonly #controllers = new Set<AbortController>();

  constructor(organizationId: string) {
    if (!organizationId) throw new Error("QUERY_CACHE_ORGANIZATION_REQUIRED");
    this.#organizationId = organizationId;
  }

  get organizationId(): string {
    return this.#organizationId;
  }

  key(parts: readonly QueryKeyPart[]): string {
    return JSON.stringify([this.#organizationId, ...parts]);
  }

  get<T>(parts: readonly QueryKeyPart[], now = Date.now()): T | undefined {
    const key = this.key(parts);
    const entry = this.#cache.get(key) as CacheEntry<T> | undefined;
    if (!entry) return undefined;
    if (entry.expires_at <= now) {
      this.#cache.delete(key);
      return undefined;
    }
    return entry.value;
  }

  set<T>(
    parts: readonly QueryKeyPart[],
    value: T,
    ttlMs = 30_000,
    now = Date.now(),
  ): void {
    this.#cache.set(this.key(parts), {
      value,
      expires_at: now + ttlMs,
    });
  }

  async fetchQuery<T>(
    parts: readonly QueryKeyPart[],
    loader: (signal: AbortSignal) => Promise<T>,
    ttlMs = 30_000,
  ): Promise<T> {
    const cached = this.get<T>(parts);
    if (cached !== undefined) return cached;

    const organizationAtStart = this.#organizationId;
    const controller = new AbortController();
    this.#controllers.add(controller);

    try {
      const value = await loader(controller.signal);
      if (
        this.#organizationId !== organizationAtStart ||
        controller.signal.aborted
      ) {
        throw new Error("QUERY_SCOPE_CHANGED");
      }
      this.set(parts, value, ttlMs);
      return value;
    } finally {
      this.#controllers.delete(controller);
    }
  }

  switchOrganization(nextOrganizationId: string): void {
    if (!nextOrganizationId) {
      throw new Error("QUERY_CACHE_ORGANIZATION_REQUIRED");
    }
    if (nextOrganizationId === this.#organizationId) return;

    this.abortInFlight();
    this.#cache.clear();
    this.#organizationId = nextOrganizationId;
  }

  clear(): void {
    this.#cache.clear();
  }

  abortInFlight(): void {
    for (const controller of this.#controllers) {
      controller.abort("organization-switch");
    }
    this.#controllers.clear();
  }
}
