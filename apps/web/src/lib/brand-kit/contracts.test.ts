import { describe, expect, it } from "vitest";
import { contrastRatio, draftPublishIssues, duplicateColorTokenIds, normalizeHexColor } from "./contracts";
import { getBrandKitBootstrap } from "./brand-kit-server";

function detail() {
  const previous = process.env.LUMI_BRAND_KIT_E2E;
  process.env.LUMI_BRAND_KIT_E2E = "1";
  const bootstrap = getBrandKitBootstrap();
  if (previous === undefined) delete process.env.LUMI_BRAND_KIT_E2E;
  else process.env.LUMI_BRAND_KIT_E2E = previous;
  if (!bootstrap.seed) throw new Error("test seed missing");
  return structuredClone(bootstrap.seed.detail);
}

describe("Brand Kit validation contracts", () => {
  it("normalizes HEX and computes accessibility contrast without inventing brand tokens", () => {
    expect(normalizeHexColor("#da4")).toBe("#DDAA44");
    expect(normalizeHexColor("#1c1917")).toBe("#1C1917");
    expect(normalizeHexColor("not-a-color")).toBeNull();
    expect(contrastRatio("#1C1917", "#FFFFFF")).toBeGreaterThan(14);
  });

  it("flags duplicate palette values", () => {
    const current = detail();
    const tokenSet = {
      ...current.draft_token_set,
      colors: [
        ...current.draft_token_set.colors,
        { id: "duplicate", name: "Duplicate", value: "#1c1917", roles: ["accent"] },
      ],
    };
    expect(duplicateColorTokenIds(tokenSet)).toContain("color-ink");
    expect(duplicateColorTokenIds(tokenSet)).toContain("duplicate");
  });

  it("blocks publication when an active font has unknown rights", () => {
    const current = detail();
    const withUnknownRights = {
      ...current,
      fonts: current.fonts.map((font) =>
        font.asset_id === "asset-font-lumi-grotesk"
          ? { ...font, rights_assertion: "UNKNOWN" as const }
          : font,
      ),
    };
    expect(draftPublishIssues(withUnknownRights).some((issue) => /UNKNOWN/.test(issue))).toBe(true);
  });
});
