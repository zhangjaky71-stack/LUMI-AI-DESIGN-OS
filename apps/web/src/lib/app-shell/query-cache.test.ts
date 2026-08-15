import { describe, expect, it } from "vitest";
import { OrgScopedQueryCache } from "./query-cache";

describe("OrgScopedQueryCache", () => {
  it("includes organization id in every cache key and clears values on switch", () => {
    const cache = new OrgScopedQueryCache("org-a");
    cache.set(["projects"], ["a"]);
    expect(cache.key(["projects"])).toBe('["org-a","projects"]');
    expect(cache.get(["projects"])).toEqual(["a"]);
    cache.switchOrganization("org-b");
    expect(cache.key(["projects"])).toBe('["org-b","projects"]');
    expect(cache.get(["projects"])).toBeUndefined();
  });

  it("aborts old in-flight queries before accepting a new organization", async () => {
    const cache = new OrgScopedQueryCache("org-a");
    const pending = cache.fetchQuery(["projects"], (signal) => new Promise<string>((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(new Error("aborted")), { once: true });
    }));
    cache.switchOrganization("org-b");
    await expect(pending).rejects.toThrow("aborted");
    expect(cache.organizationId).toBe("org-b");
  });
});
