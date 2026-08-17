import type { DesignDocument } from "./types";

const NON_SEMANTIC_METADATA_KEYS = new Set([
  "updated_at",
  "last_accessed_at",
  "selection",
  "viewport",
  "cursor",
  "document_version",
  "applied_operation_ids",
  "command_history",
]);

const ROUND_SCALE = 1_000_000_000_000;

function canonicalNumber(value: number): string {
  if (!Number.isFinite(value)) throw new Error("IR_SCHEMA_INVALID: non-finite number");
  const rounded = Math.round(value * ROUND_SCALE) / ROUND_SCALE;
  if (Object.is(rounded, -0) || Math.abs(rounded) < 1 / ROUND_SCALE) return "0";
  if (Number.isInteger(rounded)) return String(rounded);
  return rounded.toFixed(12).replace(/0+$/, "").replace(/\.$/, "");
}

function normalizeObjectEntries(value: object): ReadonlyArray<readonly [string, unknown]> {
  return Object.entries(value)
    .filter(([, child]) => child !== undefined)
    .map(([key, child]) => [key.normalize("NFC"), child] as const)
    .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0));
}

export function canonicalStringify(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "string") return JSON.stringify(value.normalize("NFC"));
  if (typeof value === "number") return canonicalNumber(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) return `[${value.map(canonicalStringify).join(",")}]`;
  if (typeof value === "object") {
    return `{${normalizeObjectEntries(value)
      .map(([key, child]) => `${JSON.stringify(key)}:${canonicalStringify(child)}`)
      .join(",")}}`;
  }
  throw new Error(`IR_SCHEMA_INVALID: unsupported canonical value ${typeof value}`);
}

export function canonicalize(document: DesignDocument): string {
  const cloned = structuredClone(document) as DesignDocument;
  const metadata = Object.fromEntries(
    Object.entries(cloned.metadata).filter(
      ([key]) =>
        !NON_SEMANTIC_METADATA_KEYS.has(key) &&
        !key.startsWith("ephemeral:") &&
        !key.startsWith("_ephemeral"),
    ),
  );
  return canonicalStringify({ ...cloned, metadata });
}

export async function hashDocument(document: DesignDocument): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalize(document));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
