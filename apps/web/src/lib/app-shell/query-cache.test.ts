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
    const pending = cache.fetchQuery(
      ["projects"],
      (signal) =>
        new Promise<string>((_resolve, reject) => {
          signal.addEventListener(
            "abort",
            () => reject(new Error("aborted")),
            { once: true },
          );
        }),
    );

    cache.switchOrganization("org-b");
    await expect(pending).rejects.toThrow("aborted");
    expect(cache.organizationId).toBe("org-b");
  });

  it("rejects a stale result even when a loader ignores AbortSignal", async () => {
    const cache = new OrgScopedQueryCache("org-a");
    let resolveLoader!: (value: string) => void;
    const pending = cache.fetchQuery(
      ["projects"],
      () =>
        new Promise<string>((resolve) => {
          resolveLoader = resolve;
        }),
    );

    cache.switchOrganization("org-b");
    resolveLoader("stale-org-a-value");

    await expect(pending).rejects.toThrow("QUERY_SCOPE_CHANGED");
    expect(cache.get(["projects"])).toBeUndefined();
  });
});
