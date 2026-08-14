import type { DesignDocument, DesignOperation, ExecutionResult } from "./types";
import { executeOperations } from "./executor";

export interface HistoryEntry {
  readonly before: DesignDocument;
  readonly after: DesignDocument;
  readonly operations: readonly DesignOperation[];
}

export class DesignIrHistory {
  private entries: HistoryEntry[] = [];
  private cursor = 0;

  apply(document: DesignDocument, operations: readonly DesignOperation[]): ExecutionResult {
    const result = executeOperations(document, operations);
    if (!result.ok) return result;
    this.entries = this.entries.slice(0, this.cursor);
    this.entries.push({
      before: structuredClone(document),
      after: structuredClone(result.document),
      operations: structuredClone(operations),
    });
    this.cursor = this.entries.length;
    return result;
  }

  canUndo(): boolean {
    return this.cursor > 0;
  }

  canRedo(): boolean {
    return this.cursor < this.entries.length;
  }

  undo(): DesignDocument | undefined {
    if (!this.canUndo()) return undefined;
    this.cursor -= 1;
    return structuredClone(this.entries[this.cursor]!.before);
  }

  redo(): DesignDocument | undefined {
    if (!this.canRedo()) return undefined;
    const document = structuredClone(this.entries[this.cursor]!.after);
    this.cursor += 1;
    return document;
  }

  snapshot(): readonly HistoryEntry[] {
    return structuredClone(this.entries);
  }
}
