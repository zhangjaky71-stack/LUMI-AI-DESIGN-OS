import {
  getDocumentVersion,
  type DesignDocument,
  type DesignNode,
  type DesignOperation,
} from "../../design-ir/src/index";
import {
  guardedExecute,
  type ConstraintOverrideToken,
  type DesignConstraint,
  type GuardedExecutionResult,
} from "../../design-constraints/src/index";

export interface CanvasCommandResult {
  readonly accepted: boolean;
  readonly document: DesignDocument;
  readonly guarded: GuardedExecutionResult;
}

interface HistoryEntry {
  readonly label: string;
  readonly forward: readonly DesignOperation[];
  readonly inverse: readonly DesignOperation[];
}

function readPath(node: DesignNode, path: string): unknown {
  let current: unknown = node;
  for (const key of path.split(".").filter(Boolean)) {
    if (current === null || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[key];
  }
  return current;
}

function operation(
  source: DesignOperation,
  id: string,
  type: DesignOperation["type"],
  targetIds: readonly string[],
  payload: Readonly<Record<string, unknown>>,
): DesignOperation {
  return {
    operation_id: id,
    type,
    target_ids: targetIds,
    expected_document_version: 0,
    payload,
    reason: `undo:${source.operation_id}`,
  };
}

function subtree(document: DesignDocument, rootId: string): DesignNode[] {
  const result: DesignNode[] = [];
  const visit = (id: string): void => {
    const node = document.nodes[id];
    if (!node) return;
    result.push(node);
    for (const childId of node.children) visit(childId);
  };
  visit(rootId);
  return result;
}

function invertOne(document: DesignDocument, source: DesignOperation, sequence: number): DesignOperation[] {
  const prefix = `inverse-${source.operation_id}-${sequence}`;
  switch (source.type) {
    case "MOVE_NODE":
      return source.target_ids.flatMap((id, index) => {
        const node = document.nodes[id];
        return node
          ? [operation(source, `${prefix}-${index}`, "MOVE_NODE", [id], { x: node.transform?.x ?? 0, y: node.transform?.y ?? 0 })]
          : [];
      });
    case "RESIZE_NODE":
      return source.target_ids.flatMap((id, index) => {
        const node = document.nodes[id];
        return node
          ? [operation(source, `${prefix}-${index}`, "RESIZE_NODE", [id], { width: node.transform?.width ?? 0, height: node.transform?.height ?? 0 })]
          : [];
      });
    case "ROTATE_NODE":
      return source.target_ids.flatMap((id, index) => {
        const node = document.nodes[id];
        return node
          ? [operation(source, `${prefix}-${index}`, "ROTATE_NODE", [id], { rotation_deg: node.transform?.rotation_deg ?? 0 })]
          : [];
      });
    case "SET_TEXT":
      return source.target_ids.flatMap((id, index) => {
        const node = document.nodes[id];
        return node
          ? [operation(source, `${prefix}-${index}`, "SET_TEXT", [id], { content: typeof node.content === "string" ? node.content : "" })]
          : [];
      });
    case "REPLACE_ASSET":
      return source.target_ids.flatMap((id, index) => {
        const node = document.nodes[id];
        if (!node) return [];
        return [operation(source, `${prefix}-${index}`, "SET_PROPERTY", [id], { path: "asset_id", value: typeof node.asset_id === "string" ? node.asset_id : null })];
      });
    case "APPLY_STYLE":
      return source.target_ids.flatMap((id, index) => {
        const node = document.nodes[id];
        if (!node) return [];
        return [operation(source, `${prefix}-${index}`, "SET_PROPERTY", [id], { path: "style_refs", value: [...(node.style_refs ?? [])] })];
      });
    case "SET_PROPERTY": {
      const path = source.payload.path;
      if (typeof path !== "string") return [];
      return source.target_ids.flatMap((id, index) => {
        const node = document.nodes[id];
        if (!node) return [];
        return [operation(source, `${prefix}-${index}`, "SET_PROPERTY", [id], { path, value: structuredClone(readPath(node, path)) ?? null })];
      });
    }
    case "CREATE_NODE": {
      const raw = source.payload.node;
      const id = raw && typeof raw === "object" && typeof (raw as { id?: unknown }).id === "string"
        ? (raw as { id: string }).id
        : source.target_ids[0];
      return id ? [operation(source, prefix, "DELETE_NODE", [id], {})] : [];
    }
    case "DELETE_NODE": {
      const restored: DesignOperation[] = [];
      let index = 0;
      for (const targetId of source.target_ids) {
        for (const node of subtree(document, targetId)) {
          if (!node.parent_id) continue;
          const parent = document.nodes[node.parent_id];
          const childIndex = parent?.children.indexOf(node.id) ?? -1;
          restored.push(
            operation(source, `${prefix}-${index++}`, "CREATE_NODE", [node.id], {
              node: structuredClone(node),
              parent_id: node.parent_id,
              ...(childIndex >= 0 ? { index: childIndex } : {}),
            }),
          );
        }
      }
      return restored;
    }
    case "REORDER_NODE":
      return source.target_ids.flatMap((id, index) => {
        const node = document.nodes[id];
        if (!node?.parent_id) return [];
        const parent = document.nodes[node.parent_id];
        return [operation(source, `${prefix}-${index}`, "REORDER_NODE", [id], { index: parent?.children.indexOf(id) ?? 0 })];
      });
    case "REPARENT_NODE":
      return source.target_ids.flatMap((id, index) => {
        const node = document.nodes[id];
        if (!node?.parent_id) return [];
        const parent = document.nodes[node.parent_id];
        return [operation(source, `${prefix}-${index}`, "REPARENT_NODE", [id], { parent_id: node.parent_id, index: parent?.children.indexOf(id) ?? 0 })];
      });
    case "BATCH": {
      const nested = Array.isArray(source.payload.operations)
        ? (source.payload.operations as DesignOperation[])
        : [];
      return invertOperations(document, nested);
    }
    default:
      return [];
  }
}

export function invertOperations(
  document: DesignDocument,
  operations: readonly DesignOperation[],
): DesignOperation[] {
  return [...operations]
    .reverse()
    .flatMap((source, index) => invertOne(document, source, index));
}

function rehydrateOperations(
  operations: readonly DesignOperation[],
  version: number,
  replayPrefix: string,
): DesignOperation[] {
  return operations.map((source, index) => ({
    ...source,
    operation_id: `${replayPrefix}-${index}-${source.operation_id}`,
    expected_document_version: version,
    ...(source.type === "BATCH" && Array.isArray(source.payload.operations)
      ? {
          payload: {
            ...source.payload,
            operations: rehydrateOperations(source.payload.operations as DesignOperation[], version, `${replayPrefix}-${index}`),
          },
        }
      : {}),
  }));
}

export class CanvasCommandBus {
  #document: DesignDocument;
  readonly #undo: HistoryEntry[] = [];
  readonly #redo: HistoryEntry[] = [];
  readonly #historyLimit: number;

  constructor(document: DesignDocument, historyLimit = 200) {
    this.#document = document;
    this.#historyLimit = historyLimit;
  }

  get document(): DesignDocument {
    return this.#document;
  }

  replaceDocument(document: DesignDocument, clearHistory = true): void {
    this.#document = document;
    if (clearHistory) {
      this.#undo.length = 0;
      this.#redo.length = 0;
    }
  }

  dispatch(
    label: string,
    operations: readonly DesignOperation[],
    constraints: readonly DesignConstraint[],
    overrides: readonly ConstraintOverrideToken[] = [],
  ): CanvasCommandResult {
    if (!operations.length) return this.#noop();
    const version = getDocumentVersion(this.#document);
    const prepared = rehydrateOperations(operations, version, `dispatch-${version}`);
    const inverse = invertOperations(this.#document, prepared);
    const result = guardedExecute(this.#document, prepared, constraints, { overrides });
    if (result.preflight.decision === "DENY" || !result.execution?.ok) {
      return { accepted: false, document: this.#document, guarded: result };
    }
    const before = this.#document;
    this.#document = result.execution.document;
    this.#undo.push({ label, forward: prepared, inverse });
    if (this.#undo.length > this.#historyLimit) this.#undo.shift();
    this.#redo.length = 0;
    void before;
    return { accepted: true, document: this.#document, guarded: result };
  }

  undo(
    constraints: readonly DesignConstraint[],
    overrides: readonly ConstraintOverrideToken[] = [],
  ): CanvasCommandResult {
    const entry = this.#undo[this.#undo.length - 1];
    if (!entry) return this.#noop();
    const result = this.#replay(entry.inverse, `undo-${getDocumentVersion(this.#document)}`, constraints, overrides);
    if (result.accepted) {
      this.#undo.pop();
      this.#redo.push(entry);
    }
    return result;
  }

  redo(
    constraints: readonly DesignConstraint[],
    overrides: readonly ConstraintOverrideToken[] = [],
  ): CanvasCommandResult {
    const entry = this.#redo[this.#redo.length - 1];
    if (!entry) return this.#noop();
    const result = this.#replay(entry.forward, `redo-${getDocumentVersion(this.#document)}`, constraints, overrides);
    if (result.accepted) {
      this.#redo.pop();
      this.#undo.push(entry);
    }
    return result;
  }

  get canUndo(): boolean {
    return this.#undo.length > 0;
  }

  get canRedo(): boolean {
    return this.#redo.length > 0;
  }

  #replay(
    operations: readonly DesignOperation[],
    prefix: string,
    constraints: readonly DesignConstraint[],
    overrides: readonly ConstraintOverrideToken[],
  ): CanvasCommandResult {
    const prepared = rehydrateOperations(operations, getDocumentVersion(this.#document), prefix);
    const guarded = guardedExecute(this.#document, prepared, constraints, { overrides });
    if (guarded.preflight.decision === "DENY" || !guarded.execution?.ok) {
      return { accepted: false, document: this.#document, guarded };
    }
    this.#document = guarded.execution.document;
    return { accepted: true, document: this.#document, guarded };
  }

  #noop(): CanvasCommandResult {
    return {
      accepted: true,
      document: this.#document,
      guarded: {
        preflight: {
          decision: "ALLOW",
          violations: [],
          conflicts: [],
          effective_constraint_ids: [],
        },
      },
    };
  }
}
