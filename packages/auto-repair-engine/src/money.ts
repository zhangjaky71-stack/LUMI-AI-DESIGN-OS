const USD = /^(0|[1-9]\d*)(?:\.(\d{1,6}))?$/;
const SCALE = 1_000_000n;

export function parseUsdMicros(value: string): bigint {
  const match = USD.exec(value);
  if (!match) throw new Error(`AUTO_REPAIR_INVALID_USD:${value}`);
  const whole = BigInt(match[1]!);
  const fraction = (match[2] ?? "").padEnd(6, "0");
  return whole * SCALE + BigInt(fraction || "0");
}

export function formatUsdMicros(value: bigint): string {
  if (value < 0n) throw new Error("AUTO_REPAIR_NEGATIVE_USD");
  const whole = value / SCALE;
  const fraction = (value % SCALE).toString().padStart(6, "0").replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : whole.toString();
}

export function addUsd(a: string, b: string): string {
  return formatUsdMicros(parseUsdMicros(a) + parseUsdMicros(b));
}

export function canAfford(available: string, required: string): boolean {
  return parseUsdMicros(available) >= parseUsdMicros(required);
}

export function remainingUsd(limit: string, spent: string): string {
  const result = parseUsdMicros(limit) - parseUsdMicros(spent);
  return formatUsdMicros(result > 0n ? result : 0n);
}
