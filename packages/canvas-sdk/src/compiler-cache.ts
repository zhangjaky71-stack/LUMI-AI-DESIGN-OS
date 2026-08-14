import {
  canonicalSha256,
  canonicalStringify,
  type DesignDocument,
} from "../../design-ir/src/index";
import type { CompiledSceneSnapshot } from "./compiler-types";

export async function canvasCompilerCacheKey(
  compilerVersion: string,
  document: DesignDocument,
): Promise<string> {
  return canonicalSha256({
    compiler_version: compilerVersion,
    document: JSON.parse(canonicalStringify(document)),
  });
}

export class CanvasCompilerCache {
  readonly #entries = new Map<string, CompiledSceneSnapshot>();
  readonly #capacity: number;

  constructor(capacity = 16) {
    if (!Number.isInteger(capacity) || capacity <= 0) {
      throw new Error("compiler cache capacity must be a positive integer");
    }
    this.#capacity = capacity;
  }

  get(key: string): CompiledSceneSnapshot | null {
    const value = this.#entries.get(key);
    if (!value) return null;
    this.#entries.delete(key);
    this.#entries.set(key, value);
    return value;
  }

  set(key: string, snapshot: CompiledSceneSnapshot): void {
    this.#entries.delete(key);
    this.#entries.set(key, snapshot);
    while (this.#entries.size > this.#capacity) {
      const oldest = this.#entries.keys().next().value as string | undefined;
      if (!oldest) break;
      this.#entries.delete(oldest);
    }
  }

  clear(): void {
    this.#entries.clear();
  }

  get size(): number {
    return this.#entries.size;
  }
}
