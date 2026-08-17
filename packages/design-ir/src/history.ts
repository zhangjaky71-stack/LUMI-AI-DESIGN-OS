import type { DesignDocument, OperationExecution } from "./types";

export interface HistoryEntry {
  readonly operation_ids: readonly string[];
  readonly before: DesignDocument;
  readonly after: DesignDocument;
}

export class CommandHistory {
  #entries: HistoryEntry[] = [];
  #cursor = 0;

  push(before: DesignDocument, execution: OperationExecution): void {
    this.#entries = this.#entries.slice(0, this.#cursor);
    this.#entries.push({
      operation_ids: [...execution.applied_operation_ids],
      before: structuredClone(before),
      after: structuredClone(execution.document),
    });
    this.#cursor = this.#entries.length;
  }

  undo(current: DesignDocument): DesignDocument {
    if (this.#cursor === 0) return structuredClone(current);
    this.#cursor -= 1;
    return structuredClone(this.#entries[this.#cursor]!.before);
  }

  redo(current: DesignDocument): DesignDocument {
    if (this.#cursor >= this.#entries.length) return structuredClone(current);
    const result = structuredClone(this.#entries[this.#cursor]!.after);
    this.#cursor += 1;
    return result;
  }

  get size(): number {
    return this.#entries.length;
  }

  get cursor(): number {
    return this.#cursor;
  }
}
