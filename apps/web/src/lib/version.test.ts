import { describe, expect, it } from "vitest";
import { buildLabel } from "./version";

describe("buildLabel", () => {
  it("formats the development version", () => {
    expect(buildLabel("0.0.0-dev")).toBe("LUMI 0.0.0-dev");
  });
});
