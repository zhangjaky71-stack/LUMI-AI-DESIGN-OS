import { safeZipEntryName } from "./export-security";

export interface ZipEntry {
  readonly name: string;
  readonly bytes: Uint8Array;
}

const encoder = new TextEncoder();

function concat(chunks: readonly Uint8Array[]): Uint8Array {
  const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const output = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.length;
  }
  return output;
}

function u16(value: number): Uint8Array {
  return new Uint8Array([value & 0xff, (value >>> 8) & 0xff]);
}

function u32(value: number): Uint8Array {
  return new Uint8Array([
    value & 0xff,
    (value >>> 8) & 0xff,
    (value >>> 16) & 0xff,
    (value >>> 24) & 0xff,
  ]);
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      const mask = -(crc & 1);
      crc = (crc >>> 1) ^ (0xedb88320 & mask);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

export function writeStoreZip(entries: readonly ZipEntry[]): Uint8Array {
  if (!entries.length) throw new Error("EXPORT_ZIP_ENTRIES_REQUIRED");
  const normalized = entries.map((entry) => ({ ...entry, name: safeZipEntryName(entry.name) }));
  if (new Set(normalized.map((entry) => entry.name)).size !== normalized.length) {
    throw new Error("EXPORT_ZIP_ENTRY_DUPLICATE");
  }
  const localChunks: Uint8Array[] = [];
  const centralChunks: Uint8Array[] = [];
  let localOffset = 0;
  for (const entry of normalized) {
    const name = encoder.encode(entry.name);
    const checksum = crc32(entry.bytes);
    const localHeader = concat([
      u32(0x04034b50),
      u16(20),
      u16(0x0800),
      u16(0),
      u16(0),
      u16(0x0021),
      u32(checksum),
      u32(entry.bytes.length),
      u32(entry.bytes.length),
      u16(name.length),
      u16(0),
      name,
    ]);
    localChunks.push(localHeader, entry.bytes);
    centralChunks.push(concat([
      u32(0x02014b50),
      u16(20),
      u16(20),
      u16(0x0800),
      u16(0),
      u16(0),
      u16(0x0021),
      u32(checksum),
      u32(entry.bytes.length),
      u32(entry.bytes.length),
      u16(name.length),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(0),
      u32(localOffset),
      name,
    ]));
    localOffset += localHeader.length + entry.bytes.length;
  }
  const central = concat(centralChunks);
  const eocd = concat([
    u32(0x06054b50),
    u16(0),
    u16(0),
    u16(normalized.length),
    u16(normalized.length),
    u32(central.length),
    u32(localOffset),
    u16(0),
  ]);
  return concat([...localChunks, central, eocd]);
}

function readU16(bytes: Uint8Array, offset: number): number {
  return bytes[offset]! | (bytes[offset + 1]! << 8);
}

function readU32(bytes: Uint8Array, offset: number): number {
  return (bytes[offset]! | (bytes[offset + 1]! << 8) | (bytes[offset + 2]! << 16) | (bytes[offset + 3]! << 24)) >>> 0;
}

export function inspectZipEntries(bytes: Uint8Array): readonly string[] {
  if (bytes.length < 22) throw new Error("EXPORT_ZIP_TOO_SMALL");
  const names: string[] = [];
  let offset = 0;
  while (offset + 4 <= bytes.length) {
    const signature = readU32(bytes, offset);
    if (signature === 0x04034b50) {
      if (offset + 30 > bytes.length) throw new Error("EXPORT_ZIP_LOCAL_HEADER_TRUNCATED");
      const compressedSize = readU32(bytes, offset + 18);
      const nameLength = readU16(bytes, offset + 26);
      const extraLength = readU16(bytes, offset + 28);
      const nameStart = offset + 30;
      const dataStart = nameStart + nameLength + extraLength;
      if (dataStart + compressedSize > bytes.length) throw new Error("EXPORT_ZIP_ENTRY_TRUNCATED");
      const name = new TextDecoder().decode(bytes.slice(nameStart, nameStart + nameLength));
      const safe = safeZipEntryName(name);
      if (safe !== name) throw new Error("EXPORT_ZIP_ENTRY_NONCANONICAL");
      names.push(name);
      offset = dataStart + compressedSize;
      continue;
    }
    if (signature === 0x02014b50 || signature === 0x06054b50) break;
    throw new Error("EXPORT_ZIP_SIGNATURE_INVALID");
  }
  if (!names.length) throw new Error("EXPORT_ZIP_NO_ENTRIES");
  if (new Set(names).size !== names.length) throw new Error("EXPORT_ZIP_ENTRY_DUPLICATE");
  return names;
}
