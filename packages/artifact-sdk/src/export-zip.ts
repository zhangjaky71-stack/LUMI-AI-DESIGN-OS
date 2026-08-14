import { safeZipEntryName } from "./export-security";

export interface ZipEntry {
  readonly name: string;
  readonly bytes: Uint8Array;
}

interface ParsedEntry extends ZipEntry {
  readonly crc32: number;
  readonly local_offset: number;
}

const encoder = new TextEncoder();
const decoder = new TextDecoder();

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
  return new Uint8Array([value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff]);
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

function readU16(bytes: Uint8Array, offset: number): number {
  if (offset < 0 || offset + 2 > bytes.length) throw new Error("EXPORT_ZIP_READ_BOUNDS");
  return bytes[offset]! | (bytes[offset + 1]! << 8);
}

function readU32(bytes: Uint8Array, offset: number): number {
  if (offset < 0 || offset + 4 > bytes.length) throw new Error("EXPORT_ZIP_READ_BOUNDS");
  return (bytes[offset]! | (bytes[offset + 1]! << 8) | (bytes[offset + 2]! << 16) | (bytes[offset + 3]! << 24)) >>> 0;
}

export function writeStoreZip(entries: readonly ZipEntry[]): Uint8Array {
  if (!entries.length) throw new Error("EXPORT_ZIP_ENTRIES_REQUIRED");
  if (entries.length > 65535) throw new Error("EXPORT_ZIP_ENTRY_LIMIT");
  const normalized = entries.map((entry) => ({ name: safeZipEntryName(entry.name), bytes: Uint8Array.from(entry.bytes) }));
  if (new Set(normalized.map((entry) => entry.name)).size !== normalized.length) throw new Error("EXPORT_ZIP_ENTRY_DUPLICATE");
  const localChunks: Uint8Array[] = [];
  const centralChunks: Uint8Array[] = [];
  let localOffset = 0;
  for (const entry of normalized) {
    const name = encoder.encode(entry.name);
    if (name.length > 65535) throw new Error("EXPORT_ZIP_ENTRY_NAME_TOO_LONG");
    const checksum = crc32(entry.bytes);
    const localHeader = concat([
      u32(0x04034b50), u16(20), u16(0x0800), u16(0), u16(0), u16(0x0021),
      u32(checksum), u32(entry.bytes.length), u32(entry.bytes.length), u16(name.length), u16(0), name,
    ]);
    localChunks.push(localHeader, entry.bytes);
    centralChunks.push(concat([
      u32(0x02014b50), u16(20), u16(20), u16(0x0800), u16(0), u16(0), u16(0x0021),
      u32(checksum), u32(entry.bytes.length), u32(entry.bytes.length), u16(name.length),
      u16(0), u16(0), u16(0), u16(0), u32(0), u32(localOffset), name,
    ]));
    localOffset += localHeader.length + entry.bytes.length;
  }
  const central = concat(centralChunks);
  const eocd = concat([
    u32(0x06054b50), u16(0), u16(0), u16(normalized.length), u16(normalized.length),
    u32(central.length), u32(localOffset), u16(0),
  ]);
  return concat([...localChunks, central, eocd]);
}

function findEocd(bytes: Uint8Array): number {
  for (let offset = bytes.length - 22; offset >= Math.max(0, bytes.length - 65557); offset -= 1) {
    if (readU32(bytes, offset) === 0x06054b50) return offset;
  }
  throw new Error("EXPORT_ZIP_EOCD_MISSING");
}

function parseLocalEntries(bytes: Uint8Array, centralOffset: number): ParsedEntry[] {
  const entries: ParsedEntry[] = [];
  let offset = 0;
  while (offset < centralOffset) {
    if (readU32(bytes, offset) !== 0x04034b50) throw new Error("EXPORT_ZIP_LOCAL_SIGNATURE_INVALID");
    if (readU16(bytes, offset + 8) !== 0) throw new Error("EXPORT_ZIP_COMPRESSION_UNSUPPORTED");
    const checksum = readU32(bytes, offset + 14);
    const compressedSize = readU32(bytes, offset + 18);
    const uncompressedSize = readU32(bytes, offset + 22);
    if (compressedSize !== uncompressedSize) throw new Error("EXPORT_ZIP_STORE_SIZE_MISMATCH");
    const nameLength = readU16(bytes, offset + 26);
    const extraLength = readU16(bytes, offset + 28);
    const nameStart = offset + 30;
    const dataStart = nameStart + nameLength + extraLength;
    const dataEnd = dataStart + compressedSize;
    if (dataEnd > centralOffset) throw new Error("EXPORT_ZIP_ENTRY_TRUNCATED");
    const name = decoder.decode(bytes.slice(nameStart, nameStart + nameLength));
    if (safeZipEntryName(name) !== name) throw new Error("EXPORT_ZIP_ENTRY_NONCANONICAL");
    const data = bytes.slice(dataStart, dataEnd);
    if (crc32(data) !== checksum) throw new Error("EXPORT_ZIP_CRC_MISMATCH");
    entries.push({ name, bytes: data, crc32: checksum, local_offset: offset });
    offset = dataEnd;
  }
  if (offset !== centralOffset) throw new Error("EXPORT_ZIP_CENTRAL_OFFSET_MISMATCH");
  return entries;
}

function validateCentralDirectory(bytes: Uint8Array, centralOffset: number, centralSize: number, local: readonly ParsedEntry[]): void {
  let offset = centralOffset;
  const seen: string[] = [];
  for (const expected of local) {
    if (readU32(bytes, offset) !== 0x02014b50) throw new Error("EXPORT_ZIP_CENTRAL_SIGNATURE_INVALID");
    if (readU16(bytes, offset + 10) !== 0) throw new Error("EXPORT_ZIP_CENTRAL_COMPRESSION_UNSUPPORTED");
    const checksum = readU32(bytes, offset + 16);
    const compressedSize = readU32(bytes, offset + 20);
    const uncompressedSize = readU32(bytes, offset + 24);
    const nameLength = readU16(bytes, offset + 28);
    const extraLength = readU16(bytes, offset + 30);
    const commentLength = readU16(bytes, offset + 32);
    const localOffset = readU32(bytes, offset + 42);
    const nameStart = offset + 46;
    const name = decoder.decode(bytes.slice(nameStart, nameStart + nameLength));
    if (name !== expected.name || checksum !== expected.crc32 || compressedSize !== expected.bytes.length || uncompressedSize !== expected.bytes.length || localOffset !== expected.local_offset) {
      throw new Error("EXPORT_ZIP_CENTRAL_LOCAL_MISMATCH");
    }
    seen.push(name);
    offset = nameStart + nameLength + extraLength + commentLength;
  }
  if (offset !== centralOffset + centralSize) throw new Error("EXPORT_ZIP_CENTRAL_SIZE_MISMATCH");
  if (new Set(seen).size !== seen.length) throw new Error("EXPORT_ZIP_ENTRY_DUPLICATE");
}

export function readStoreZipEntries(bytes: Uint8Array): ReadonlyMap<string, Uint8Array> {
  if (bytes.length < 22) throw new Error("EXPORT_ZIP_TOO_SMALL");
  const eocd = findEocd(bytes);
  const disk = readU16(bytes, eocd + 4);
  const centralDisk = readU16(bytes, eocd + 6);
  const diskEntries = readU16(bytes, eocd + 8);
  const totalEntries = readU16(bytes, eocd + 10);
  const centralSize = readU32(bytes, eocd + 12);
  const centralOffset = readU32(bytes, eocd + 16);
  const commentLength = readU16(bytes, eocd + 20);
  if (disk !== 0 || centralDisk !== 0 || diskEntries !== totalEntries) throw new Error("EXPORT_ZIP_MULTIDISK_UNSUPPORTED");
  if (eocd + 22 + commentLength !== bytes.length) throw new Error("EXPORT_ZIP_TRAILING_DATA_FORBIDDEN");
  if (centralOffset + centralSize !== eocd) throw new Error("EXPORT_ZIP_EOCD_CENTRAL_MISMATCH");
  const local = parseLocalEntries(bytes, centralOffset);
  if (local.length !== totalEntries || !local.length) throw new Error("EXPORT_ZIP_ENTRY_COUNT_MISMATCH");
  if (new Set(local.map((entry) => entry.name)).size !== local.length) throw new Error("EXPORT_ZIP_ENTRY_DUPLICATE");
  validateCentralDirectory(bytes, centralOffset, centralSize, local);
  return new Map(local.map((entry) => [entry.name, Uint8Array.from(entry.bytes)] as const));
}

export function inspectZipEntries(bytes: Uint8Array): readonly string[] {
  return [...readStoreZipEntries(bytes).keys()];
}
