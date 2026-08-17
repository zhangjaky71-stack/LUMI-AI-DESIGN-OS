import { computeSemanticDiff } from "./diff";
import {
  IrRuntimeError,
  type ConstraintPreflight,
  type DesignDocument,
  type DesignNode,
  type DesignOperation,
  type IrIssue,
  type OperationExecution,
} from "./types";
import { parseDocument, validateDocument, validateOperation } from "./validation";

function documentVersion(document: DesignDocument): number {
  const value = document.metadata.document_version;
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : 0;
}

function appliedIds(document: DesignDocument): readonly string[] {
  const value = document.metadata.applied_operation_ids;
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? value
    : [];
}

function assertExpected(document: DesignDocument, operation: DesignOperation): void {
  const version = documentVersion(document);
  if (operation.expected_document_version !== version) {
    throw new IrRuntimeError({
      code: "IR_VERSION_CONFLICT",
      message: `expected version ${operation.expected_document_version}, current ${version}`,
      operation_id: operation.operation_id,
    });
  }
}

function fail(
  code: IrIssue["code"],
  message: string,
  operation: DesignOperation,
  nodeIds: string[] = [],
): never {
  throw new IrRuntimeError({
    code,
    message,
    operation_id: operation.operation_id,
    node_ids: nodeIds,
  });
}

function targetNodes(document: DesignDocument, operation: DesignOperation): DesignNode[] {
  if (!operation.target_ids.length) {
    fail("IR_OPERATION_INVALID", "operation requires target_ids", operation);
  }
  return operation.target_ids.map((id) => {
    const node = document.nodes[id];
    if (!node) fail("IR_TARGET_NOT_FOUND", `target ${id} not found`, operation, [id]);
    return node;
  });
}

function setNode(document: DesignDocument, node: DesignNode): DesignDocument {
  return { ...document, nodes: { ...document.nodes, [node.id]: node } };
}

function removeFromParent(
  document: DesignDocument,
  node: DesignNode,
  operation: DesignOperation,
): DesignDocument {
  if (node.parent_id === null) return document;
  const parent = document.nodes[node.parent_id];
  if (!parent) {
    fail("IR_REFERENCE_MISSING", `parent ${node.parent_id} not found`, operation, [node.id]);
  }
  return setNode(document, {
    ...parent,
    children: parent.children.filter((id) => id !== node.id),
  });
}

function insertIntoParent(
  document: DesignDocument,
  nodeId: string,
  parentId: string,
  index: number | undefined,
  operation: DesignOperation,
): DesignDocument {
  const parent = document.nodes[parentId];
  if (!parent) fail("IR_REFERENCE_MISSING", `parent ${parentId} not found`, operation, [parentId]);
  const children = parent.children.filter((id) => id !== nodeId);
  const position =
    index === undefined ? children.length : Math.max(0, Math.min(index, children.length));
  const next = [...children.slice(0, position), nodeId, ...children.slice(position)];
  return setNode(document, { ...parent, children: next });
}

function subtreeIds(document: DesignDocument, id: string): Set<string> {
  const values = new Set<string>();
  const walk = (nodeId: string): void => {
    if (values.has(nodeId)) return;
    values.add(nodeId);
    for (const childId of document.nodes[nodeId]?.children ?? []) walk(childId);
  };
  walk(id);
  return values;
}

function applySingle(document: DesignDocument, operation: DesignOperation): DesignDocument {
  validateOperation(operation);
  switch (operation.type) {
    case "CREATE_NODE": {
      const raw = operation.payload.node;
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
        fail("IR_OPERATION_INVALID", "CREATE_NODE requires payload.node", operation);
      }
      const node = structuredClone(raw) as DesignNode;
      if (document.nodes[node.id]) {
        fail("IR_OPERATION_INVALID", `node ${node.id} exists`, operation, [node.id]);
      }
      if (node.parent_id === null || node.kind === "DOCUMENT_ROOT") {
        fail("IR_OPERATION_INVALID", "cannot create a second root", operation, [node.id]);
      }
      let next: DesignDocument = {
        ...document,
        nodes: { ...document.nodes, [node.id]: { ...node, children: [...node.children] } },
      };
      next = insertIntoParent(
        next,
        node.id,
        node.parent_id,
        typeof operation.payload.index === "number" ? operation.payload.index : undefined,
        operation,
      );
      return next;
    }
    case "DELETE_NODE": {
      let next = document;
      for (const node of targetNodes(next, operation)) {
        if (node.id === next.root_id) {
          fail("IR_OPERATION_INVALID", "cannot delete root", operation, [node.id]);
        }
        const removeIds = subtreeIds(next, node.id);
        next = removeFromParent(next, node, operation);
        const nodes = Object.fromEntries(
          Object.entries(next.nodes).filter(([id]) => !removeIds.has(id)),
        );
        next = { ...next, nodes };
      }
      return next;
    }
    case "SET_PROPERTY": {
      const property = operation.payload.property;
      if (typeof property !== "string" || !property || property.includes(".")) {
        fail("IR_OPERATION_INVALID", "SET_PROPERTY requires a direct property name", operation);
      }
      if (["id", "parent_id", "children", "kind"].includes(property)) {
        fail("IR_OPERATION_INVALID", `SET_PROPERTY cannot mutate ${property}`, operation);
      }
      let next = document;
      for (const node of targetNodes(next, operation)) {
        next = setNode(next, {
          ...node,
          [property]: structuredClone(operation.payload.value),
        });
      }
      return next;
    }
    case "MOVE_NODE":
    case "RESIZE_NODE":
    case "ROTATE_NODE": {
      let next = document;
      for (const node of targetNodes(next, operation)) {
        const transform = { ...(node.transform ?? {}) };
        if (operation.type === "MOVE_NODE") {
          if (
            typeof operation.payload.x !== "number" ||
            typeof operation.payload.y !== "number"
          ) {
            fail("IR_OPERATION_INVALID", "MOVE_NODE requires x/y", operation);
          }
          transform.x = operation.payload.x;
          transform.y = operation.payload.y;
        } else if (operation.type === "RESIZE_NODE") {
          if (
            typeof operation.payload.width !== "number" ||
            typeof operation.payload.height !== "number" ||
            operation.payload.width < 0 ||
            operation.payload.height < 0
          ) {
            fail(
              "IR_OPERATION_INVALID",
              "RESIZE_NODE requires non-negative width/height",
              operation,
            );
          }
          transform.width = operation.payload.width;
          transform.height = operation.payload.height;
        } else {
          if (typeof operation.payload.rotation_deg !== "number") {
            fail("IR_OPERATION_INVALID", "ROTATE_NODE requires rotation_deg", operation);
          }
          transform.rotation_deg = operation.payload.rotation_deg;
        }
        next = setNode(next, { ...node, transform });
      }
      return next;
    }
    case "REORDER_NODE": {
      const [node] = targetNodes(document, operation);
      if (!node || node.parent_id === null) {
        fail("IR_OPERATION_INVALID", "cannot reorder root", operation);
      }
      const index = operation.payload.index;
      if (!Number.isInteger(index)) {
        fail("IR_OPERATION_INVALID", "REORDER_NODE requires integer index", operation);
      }
      return insertIntoParent(document, node.id, node.parent_id, index as number, operation);
    }
    case "REPARENT_NODE": {
      const [node] = targetNodes(document, operation);
      const parentId = operation.payload.parent_id;
      if (!node || typeof parentId !== "string" || !parentId) {
        fail("IR_OPERATION_INVALID", "REPARENT_NODE requires parent_id", operation);
      }
      if (subtreeIds(document, node.id).has(parentId)) {
        fail(
          "IR_GRAPH_CYCLE",
          `cannot reparent ${node.id} into its subtree`,
          operation,
          [node.id, parentId],
        );
      }
      let next = removeFromParent(document, node, operation);
      next = setNode(next, { ...node, parent_id: parentId });
      return insertIntoParent(
        next,
        node.id,
        parentId,
        typeof operation.payload.index === "number" ? operation.payload.index : undefined,
        operation,
      );
    }
    case "REPLACE_ASSET": {
      const assetId = operation.payload.asset_id;
      if (typeof assetId !== "string" || !assetId) {
        fail("IR_OPERATION_INVALID", "REPLACE_ASSET requires asset_id", operation);
      }
      let next = document;
      for (const node of targetNodes(next, operation)) {
        next = setNode(next, { ...node, asset_id: assetId });
      }
      return next;
    }
    case "SET_TEXT": {
      const content = operation.payload.content;
      if (typeof content !== "string") {
        fail("IR_OPERATION_INVALID", "SET_TEXT requires content", operation);
      }
      let next = document;
      for (const node of targetNodes(next, operation)) {
        if (node.kind !== "TEXT") {
          fail("IR_OPERATION_INVALID", "SET_TEXT target must be TEXT", operation, [node.id]);
        }
        next = setNode(next, { ...node, content });
      }
      return next;
    }
    case "APPLY_STYLE": {
      const refs = operation.payload.style_refs;
      if (!Array.isArray(refs) || !refs.every((item) => typeof item === "string")) {
        fail("IR_OPERATION_INVALID", "APPLY_STYLE requires style_refs[]", operation);
      }
      let next = document;
      for (const node of targetNodes(next, operation)) {
        next = setNode(next, { ...node, style_refs: [...refs] });
      }
      return next;
    }
    case "BATCH":
      fail("IR_OPERATION_INVALID", "nested BATCH must be handled by applyOperation", operation);
  }
}

function batchOperations(operation: DesignOperation): readonly DesignOperation[] {
  const raw = operation.payload.operations;
  if (!Array.isArray(raw)) {
    fail("IR_OPERATION_INVALID", "BATCH requires operations[]", operation);
  }
  return structuredClone(raw) as DesignOperation[];
}

function assertNoDuplicates(
  document: DesignDocument,
  ids: readonly string[],
  operationId: string,
): void {
  const current = new Set(appliedIds(document));
  const seen = new Set<string>();
  for (const id of ids) {
    if (!id || current.has(id) || seen.has(id)) {
      throw new IrRuntimeError({
        code: "IR_OPERATION_INVALID",
        message: `duplicate operation_id ${id}`,
        operation_id: operationId,
      });
    }
    seen.add(id);
  }
}

export function applyOperation(
  document: DesignDocument,
  operation: DesignOperation,
  preflight?: ConstraintPreflight,
): OperationExecution {
  const before = parseDocument(document);
  validateOperation(operation);
  assertExpected(before, operation);
  const currentVersion = documentVersion(before);
  const operations = operation.type === "BATCH" ? batchOperations(operation) : [operation];
  const ids =
    operation.type === "BATCH"
      ? [operation.operation_id, ...operations.map((item) => item.operation_id)]
      : [operation.operation_id];
  assertNoDuplicates(before, ids, operation.operation_id);

  let working = structuredClone(before) as DesignDocument;
  try {
    for (const item of operations) {
      if (item.type === "BATCH") {
        fail("IR_OPERATION_INVALID", "nested BATCH is forbidden", item);
      }
      if (item.expected_document_version !== currentVersion) {
        throw new IrRuntimeError({
          code: "IR_VERSION_CONFLICT",
          message: `child ${item.operation_id} expected ${item.expected_document_version}, current ${currentVersion}`,
          operation_id: item.operation_id,
        });
      }
      const preflightIssues = preflight?.(working, item) ?? [];
      if (preflightIssues.length) throw new IrRuntimeError(preflightIssues[0]!);
      working = applySingle(working, item);
    }
    const issues = validateDocument(working);
    if (issues.length) throw new IrRuntimeError(issues[0]!);
  } catch (error) {
    if (
      operation.type === "BATCH" &&
      error instanceof IrRuntimeError &&
      error.code !== "IR_VERSION_CONFLICT"
    ) {
      throw new IrRuntimeError({
        code: "IR_BATCH_FAILED",
        message: error.message,
        operation_id: operation.operation_id,
        node_ids: error.node_ids,
        ...(error.pointer ? { pointer: error.pointer } : {}),
      });
    }
    throw error;
  }

  const applied = [...appliedIds(before), ...ids];
  const nextVersion = currentVersion + 1;
  working = {
    ...working,
    metadata: {
      ...working.metadata,
      document_version: nextVersion,
      applied_operation_ids: applied,
    },
  };
  return {
    document: parseDocument(working),
    previous_version: currentVersion,
    document_version: nextVersion,
    applied_operation_ids: ids,
    diff: computeSemanticDiff(before, working),
  };
}

export function applyBatch(
  document: DesignDocument,
  operations: readonly DesignOperation[],
  expectedDocumentVersion: number,
  operationId = `batch:${operations.map((item) => item.operation_id).join("+")}`,
  preflight?: ConstraintPreflight,
): OperationExecution {
  return applyOperation(
    document,
    {
      operation_id: operationId,
      type: "BATCH",
      target_ids: [],
      expected_document_version: expectedDocumentVersion,
      payload: { operations: structuredClone(operations) },
    },
    preflight,
  );
}
