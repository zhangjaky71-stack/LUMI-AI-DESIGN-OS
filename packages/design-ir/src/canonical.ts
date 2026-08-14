import type { DesignDocument } from "./types";

export const EPHEMERAL_METADATA_KEYS = new Set([
  "updated_at",
  "last_accessed_at",
  "selection",
  "viewport",
  "cursor",
]);

function assertFinite(value: unknown, path: string): void {
  if (typeof value === "number" && !Number.isFinite(value)) {
    throw new Error(`NON_FINITE_NUMBER at ${path}`);
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertFinite(item, `${path}[${index}]`));
    return;
  }
  if (value !== null && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) assertFinite(child, `${path}.${key}`);
  }
}

function normalize(value: unknown): unknown {
  if (typeof value === "string") return value.normalize("NFC");
  if (typeof value === "number") return Object.is(value, -0) ? 0 : value;
  if (Array.isArray(value)) return value.map(normalize);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([, child]) => child !== undefined)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, child]) => [key.normalize("NFC"), normalize(child)]),
    );
  }
  return value;
}

function withoutEphemeralMetadata(document: DesignDocument): DesignDocument {
  const metadata = Object.fromEntries(
    Object.entries(document.metadata).filter(
      ([key]) =>
        !EPHEMERAL_METADATA_KEYS.has(key) &&
        !key.startsWith("ephemeral:") &&
        !key.startsWith("_ephemeral"),
    ),
  );
  return { ...structuredClone(document), metadata } as DesignDocument;
}

export function canonicalStringify(value: unknown): string {
  assertFinite(value, "$");
  return JSON.stringify(normalize(value));
}

export async function canonicalSha256(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalStringify(value));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function canonicalDocument(document: DesignDocument): string {
  return canonicalStringify(withoutEphemeralMetadata(document));
}

export async function hashDocument(document: DesignDocument): Promise<string> {
  return canonicalSha256(withoutEphemeralMetadata(document));
}
