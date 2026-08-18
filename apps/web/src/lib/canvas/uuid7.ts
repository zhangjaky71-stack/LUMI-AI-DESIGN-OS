export function newUuid7(now = Date.now()): string {
  if (!Number.isInteger(now) || now < 0 || now >= 2 ** 48) {
    throw new Error("UUID7_TIMESTAMP_INVALID");
  }
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let value = BigInt(now);
  for (let index = 5; index >= 0; index -= 1) {
    bytes[index] = Number(value & 0xffn);
    value >>= 8n;
  }
  bytes[6] = (bytes[6]! & 0x0f) | 0x70;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}
