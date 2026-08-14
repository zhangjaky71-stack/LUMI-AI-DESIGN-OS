import { describe, expect, it } from "vitest";
import { addUsd, canAfford, formatUsdMicros, parseUsdMicros, remainingUsd } from "./money";

describe("NODE-51 decimal budget helpers", () => {
  it("uses integer micro-dollars instead of float arithmetic", () => {
    expect(parseUsdMicros("0.1") + parseUsdMicros("0.2")).toBe(parseUsdMicros("0.3"));
    expect(addUsd("0.1", "0.2")).toBe("0.3");
    expect(remainingUsd("1.000001", "0.999999")).toBe("0.000002");
    expect(canAfford("0.300000", "0.3")).toBe(true);
    expect(formatUsdMicros(1234567n)).toBe("1.234567");
  });

  it("rejects negative, exponent and over-precise money strings", () => {
    for (const value of ["-1", "1e-3", "0.0000001", "01.2", ""] as const) {
      expect(() => parseUsdMicros(value)).toThrow();
    }
  });
});
