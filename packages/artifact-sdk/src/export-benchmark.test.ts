import { describe, expect, it } from "vitest";
import { readStoreZipEntries, writeStoreZip } from "./export-zip";

function payload(index: number): Uint8Array {
  const bytes = new Uint8Array(8192);
  for (let offset = 0; offset < bytes.length; offset += 1) bytes[offset] = (index * 31 + offset * 17) & 0xff;
  return bytes;
}

describe("NODE-49 packaging benchmark harness", () => {
  it("packages and validates 100 deterministic export files", () => {
    const entries = Array.from({ length: 100 }, (_, index) => ({
      name: `outputs/variant-${String(index).padStart(3, "0")}.bin`,
      bytes: payload(index),
    }));
    const started = performance.now();
    const zip = writeStoreZip(entries);
    const packedMs = performance.now() - started;
    const validatedStarted = performance.now();
    const unpacked = readStoreZipEntries(zip);
    const validatedMs = performance.now() - validatedStarted;
    expect(unpacked.size).toBe(100);
    expect(zip.length).toBeGreaterThan(8192 * 100);
    expect([...unpacked.keys()][0]).toBe("outputs/variant-000.bin");
    expect([...unpacked.keys()][99]).toBe("outputs/variant-099.bin");
    expect(packedMs).toBeGreaterThanOrEqual(0);
    expect(validatedMs).toBeGreaterThanOrEqual(0);
    console.log(JSON.stringify({ entries: 100, payload_bytes: 8192 * 100, zip_bytes: zip.length, packed_ms: Math.round(packedMs * 1000) / 1000, validated_ms: Math.round(validatedMs * 1000) / 1000 }));
  });
});
