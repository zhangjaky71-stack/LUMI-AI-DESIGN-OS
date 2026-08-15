import type { DesignOperation } from "@lumi/design-ir";
import type { PendingOperationBatch } from "./types";

export function rebaseOperationsVersion(
  operations: readonly DesignOperation[],
  version: number,
  prefix = `canvas-save-${version}`,
): DesignOperation[] {
  return operations.map((source, index) => ({
    ...source,
    operation_id: `${prefix}-${index}-${source.operation_id}`,
    expected_document_version: version,
    ...(source.type === "BATCH" && Array.isArray(source.payload.operations)
      ? {
          payload: {
            ...source.payload,
            operations: rebaseOperationsVersion(
              source.payload.operations as DesignOperation[],
              version,
              `${prefix}-${index}`,
            ),
          },
        }
      : {}),
  }));
}

export class CanvasAutosaveBuffer {
  #baseVersion: number | null = null;
  readonly #operations: DesignOperation[] = [];

  get size(): number {
    return this.#operations.length;
  }

  append(serverVersion: number, operations: readonly DesignOperation[]): void {
    if (!operations.length) return;
    if (this.#baseVersion === null) this.#baseVersion = serverVersion;
    this.#operations.push(...structuredClone(operations));
  }

  snapshot(): PendingOperationBatch | null {
    if (this.#baseVersion === null || !this.#operations.length) return null;
    return {
      base_document_version: this.#baseVersion,
      operations: rebaseOperationsVersion(this.#operations, this.#baseVersion),
      count: this.#operations.length,
    };
  }

  acknowledge(count: number, nextServerVersion: number): void {
    this.#operations.splice(0, Math.max(0, count));
    this.#baseVersion = this.#operations.length ? nextServerVersion : null;
  }

  clear(): void {
    this.#operations.length = 0;
    this.#baseVersion = null;
  }
}
