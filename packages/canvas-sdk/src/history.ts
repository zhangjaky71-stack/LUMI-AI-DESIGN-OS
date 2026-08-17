import type { CanvasOperationGateway } from "./operation-gateway";
import type { OperationCommitResult, OperationDescriptor } from "./types";

export interface CanvasHistoryEntry { readonly label: string; readonly forward: readonly OperationDescriptor[]; readonly inverse: readonly OperationDescriptor[]; readonly coalesceKey?: string }

export class CanvasCommandHistory {
  private undoStack: CanvasHistoryEntry[] = [];
  private redoStack: CanvasHistoryEntry[] = [];
  push(entry: CanvasHistoryEntry): void {
    const previous = this.undoStack.at(-1);
    if (entry.coalesceKey && previous?.coalesceKey === entry.coalesceKey) {
      this.undoStack[this.undoStack.length - 1] = { ...entry, inverse: previous.inverse };
    } else this.undoStack.push(entry);
    this.redoStack = [];
  }
  undo(gateway: CanvasOperationGateway): OperationCommitResult | null {
    const entry = this.undoStack.pop(); if (!entry) return null;
    const result = gateway.commitBatch(entry.inverse, "canvas-undo");
    if (result.ok) this.redoStack.push(entry); else this.undoStack.push(entry);
    return result;
  }
  redo(gateway: CanvasOperationGateway): OperationCommitResult | null {
    const entry = this.redoStack.pop(); if (!entry) return null;
    const result = gateway.commitBatch(entry.forward, "canvas-redo");
    if (result.ok) this.undoStack.push(entry); else this.redoStack.push(entry);
    return result;
  }
  get canUndo(): boolean { return this.undoStack.length > 0; }
  get canRedo(): boolean { return this.redoStack.length > 0; }
}
