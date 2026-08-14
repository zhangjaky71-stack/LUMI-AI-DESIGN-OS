import type {
  DesignDocument,
  DesignOperation,
  DesignNode,
  ExecutionResult,
  JsonValue,
  OperationFailure,
} from "./types";
import { getDocumentVersion } from "./types";

type MutableNode = Record<string, unknown> & {
  id: string;
  kind: string;
  parent_id: string | null;
  children: string[];
};

type MutableDocument = {
  schema_version: string;
  document_id: string;
  unit: string;
  root_id: string;
  nodes: Record<string, MutableNode>;
  resources: Record<string, JsonValue>;
  metadata: Record<string, JsonValue>;
};

class OperationError extends Error {
  constructor(
    readonly failure: OperationFailure,
  ) {
    super(failure.message);
  }
}

function cloneDocument(document: DesignDocument): MutableDocument {
  return structuredClone(document) as unknown as MutableDocument;
}

function failure(
  operation: DesignOperation,
  code: OperationFailure["code"],
  message: string,
  targetId?: string,
): OperationError {
  const value: OperationFailure = targetId
    ? { operation_id: operation.operation_id, code, message, target_id: targetId }
    : { operation_id: operation.operation_id, code, message };
  return new OperationError(value);
}

function assertFinite(value: unknown, operation: DesignOperation, path = "payload"): void {
  if (typeof value === "number" && !Number.isFinite(value)) {
    throw failure(operation, "NON_FINITE_NUMBER", `${path} must contain only finite numbers`);
  }
  if (Array.isArray(value)) {
    value.forEach((child, index) => assertFinite(child, operation, `${path}[${index}]`));
  } else if (value !== null && typeof value === "object") {
    Object.entries(value).forEach(([key, child]) => assertFinite(child, operation, `${path}.${key}`));
  }
}

function nodeFor(document: MutableDocument, operation: DesignOperation, id: string): MutableNode {
  const node = document.nodes[id];
  if (!node) throw failure(operation, "TARGET_NOT_FOUND", `Node ${id} does not exist`, id);
  return node;
}

function parentFor(document: MutableDocument, operation: DesignOperation, id: string): MutableNode {
  const parent = document.nodes[id];
  if (!parent) throw failure(operation, "PARENT_NOT_FOUND", `Parent ${id} does not exist`, id);
  return parent;
}

function clampIndex(index: unknown, length: number): number {
  return typeof index === "number" && Number.isInteger(index)
    ? Math.max(0, Math.min(index, length))
    : length;
}

function removeChild(parent: MutableNode, childId: string): void {
  parent.children = parent.children.filter((id) => id !== childId);
}

function insertChild(parent: MutableNode, childId: string, index: unknown): void {
  removeChild(parent, childId);
  const position = clampIndex(index, parent.children.length);
  parent.children.splice(position, 0, childId);
}

function descendants(document: MutableDocument, rootId: string): Set<string> {
  const result = new Set<string>();
  const queue = [...(document.nodes[rootId]?.children ?? [])];
  while (queue.length) {
    const current = queue.shift();
    if (!current || result.has(current)) continue;
    result.add(current);
    queue.push(...(document.nodes[current]?.children ?? []));
  }
  return result;
}

function setPath(node: MutableNode, path: string, value: unknown): void {
  const keys = path.split(".").filter(Boolean);
  if (!keys.length) throw new Error("property path is empty");
  let current: Record<string, unknown> = node;
  for (const key of keys.slice(0, -1)) {
    const child = current[key];
    if (child === null || typeof child !== "object" || Array.isArray(child)) current[key] = {};
    current = current[key] as Record<string, unknown>;
  }
  current[keys[keys.length - 1]!] = structuredClone(value);
}

function mutateTransform(
  node: MutableNode,
  patch: Readonly<Record<string, unknown>>,
): void {
  const current =
    node.transform !== null && typeof node.transform === "object" && !Array.isArray(node.transform)
      ? (node.transform as Record<string, unknown>)
      : {};
  node.transform = { ...current, ...patch };
}

function applyCreate(document: MutableDocument, operation: DesignOperation): void {
  const raw = operation.payload.node;
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    throw failure(operation, "INVALID_OPERATION", "CREATE_NODE payload.node must be an object");
  }
  const node = structuredClone(raw) as MutableNode;
  if (typeof node.id !== "string" || !node.id || typeof node.kind !== "string") {
    throw failure(operation, "INVALID_OPERATION", "CREATE_NODE requires node.id and node.kind");
  }
  if (document.nodes[node.id]) {
    throw failure(operation, "INVALID_OPERATION", `Node ${node.id} already exists`, node.id);
  }
  const parentId =
    typeof operation.payload.parent_id === "string"
      ? operation.payload.parent_id
      : typeof node.parent_id === "string"
        ? node.parent_id
        : null;
  if (!parentId) throw failure(operation, "PARENT_NOT_FOUND", "CREATE_NODE requires a parent_id");
  const parent = parentFor(document, operation, parentId);
  node.parent_id = parentId;
  node.children = Array.isArray(node.children) ? [...node.children] : [];
  document.nodes[node.id] = node;
  insertChild(parent, node.id, operation.payload.index);
}

function applyDelete(document: MutableDocument, operation: DesignOperation): void {
  for (const id of operation.target_ids) {
    if (id === document.root_id) {
      throw failure(operation, "ROOT_MUTATION_FORBIDDEN", "The document root cannot be deleted", id);
    }
    const node = nodeFor(document, operation, id);
    const removeIds = [id, ...descendants(document, id)];
    if (node.parent_id) removeChild(parentFor(document, operation, node.parent_id), id);
    for (const removeId of removeIds) delete document.nodes[removeId];
  }
}

function applySetProperty(document: MutableDocument, operation: DesignOperation): void {
  const path = operation.payload.path;
  if (typeof path !== "string" || !path) {
    throw failure(operation, "INVALID_OPERATION", "SET_PROPERTY payload.path must be a string");
  }
  for (const id of operation.target_ids) {
    if (id === document.root_id && (path === "id" || path === "parent_id")) {
      throw failure(operation, "ROOT_MUTATION_FORBIDDEN", `Cannot mutate root ${path}`, id);
    }
    try {
      setPath(nodeFor(document, operation, id), path, operation.payload.value);
    } catch (error) {
      throw failure(
        operation,
        "INVALID_OPERATION",
        error instanceof Error ? error.message : "Invalid property mutation",
        id,
      );
    }
  }
}

function applyMove(document: MutableDocument, operation: DesignOperation): void {
  for (const id of operation.target_ids) {
    const node = nodeFor(document, operation, id);
    const current = (node.transform ?? {}) as Record<string, unknown>;
    const x = operation.payload.x;
    const y = operation.payload.y;
    const dx = operation.payload.dx;
    const dy = operation.payload.dy;
    mutateTransform(node, {
      x:
        typeof x === "number"
          ? x
          : (typeof current.x === "number" ? current.x : 0) + (typeof dx === "number" ? dx : 0),
      y:
        typeof y === "number"
          ? y
          : (typeof current.y === "number" ? current.y : 0) + (typeof dy === "number" ? dy : 0),
    });
  }
}

function applyResize(document: MutableDocument, operation: DesignOperation): void {
  if (typeof operation.payload.width !== "number" || typeof operation.payload.height !== "number") {
    throw failure(operation, "INVALID_OPERATION", "RESIZE_NODE requires numeric width and height");
  }
  for (const id of operation.target_ids) {
    mutateTransform(nodeFor(document, operation, id), {
      width: operation.payload.width,
      height: operation.payload.height,
    });
  }
}

function applyRotate(document: MutableDocument, operation: DesignOperation): void {
  if (typeof operation.payload.rotation_deg !== "number") {
    throw failure(operation, "INVALID_OPERATION", "ROTATE_NODE requires rotation_deg");
  }
  for (const id of operation.target_ids) {
    mutateTransform(nodeFor(document, operation, id), { rotation_deg: operation.payload.rotation_deg });
  }
}

function applyReorder(document: MutableDocument, operation: DesignOperation): void {
  for (const id of operation.target_ids) {
    const node = nodeFor(document, operation, id);
    if (!node.parent_id) {
      throw failure(operation, "ROOT_MUTATION_FORBIDDEN", "Root cannot be reordered", id);
    }
    insertChild(parentFor(document, operation, node.parent_id), id, operation.payload.index);
  }
}

function applyReparent(document: MutableDocument, operation: DesignOperation): void {
  const parentId = operation.payload.parent_id;
  if (typeof parentId !== "string") {
    throw failure(operation, "INVALID_OPERATION", "REPARENT_NODE requires payload.parent_id");
  }
  const nextParent = parentFor(document, operation, parentId);
  for (const id of operation.target_ids) {
    if (id === document.root_id) {
      throw failure(operation, "ROOT_MUTATION_FORBIDDEN", "Root cannot be reparented", id);
    }
    const node = nodeFor(document, operation, id);
    if (id === parentId || descendants(document, id).has(parentId)) {
      throw failure(operation, "CYCLE_DETECTED", `Reparenting ${id} under ${parentId} creates a cycle`, id);
    }
    if (node.parent_id) removeChild(parentFor(document, operation, node.parent_id), id);
    node.parent_id = parentId;
    insertChild(nextParent, id, operation.payload.index);
  }
}

function applyReplaceAsset(document: MutableDocument, operation: DesignOperation): void {
  if (typeof operation.payload.asset_id !== "string") {
    throw failure(operation, "INVALID_OPERATION", "REPLACE_ASSET requires payload.asset_id");
  }
  for (const id of operation.target_ids) nodeFor(document, operation, id).asset_id = operation.payload.asset_id;
}

function applySetText(document: MutableDocument, operation: DesignOperation): void {
  if (typeof operation.payload.content !== "string") {
    throw failure(operation, "INVALID_OPERATION", "SET_TEXT requires payload.content");
  }
  for (const id of operation.target_ids) nodeFor(document, operation, id).content = operation.payload.content;
}

function applyStyle(document: MutableDocument, operation: DesignOperation): void {
  const styleRefs = Array.isArray(operation.payload.style_refs)
    ? operation.payload.style_refs.filter((value): value is string => typeof value === "string")
    : typeof operation.payload.style_ref === "string"
      ? [operation.payload.style_ref]
      : [];
  if (!styleRefs.length) {
    throw failure(operation, "INVALID_OPERATION", "APPLY_STYLE requires style_ref or style_refs");
  }
  for (const id of operation.target_ids) nodeFor(document, operation, id).style_refs = [...styleRefs];
}

function nestedOperations(operation: DesignOperation): readonly DesignOperation[] {
  const operations = operation.payload.operations;
  if (!Array.isArray(operations)) {
    throw failure(operation, "INVALID_OPERATION", "BATCH payload.operations must be an array");
  }
  return operations as DesignOperation[];
}

function applyOne(
  document: MutableDocument,
  operation: DesignOperation,
  expectedVersion: number,
  applied: string[],
): void {
  if (operation.expected_document_version !== expectedVersion) {
    throw failure(
      operation,
      "VERSION_CONFLICT",
      `Expected document version ${operation.expected_document_version}; current version is ${expectedVersion}`,
    );
  }
  assertFinite(operation.payload, operation);
  switch (operation.type) {
    case "CREATE_NODE":
      applyCreate(document, operation);
      break;
    case "DELETE_NODE":
      applyDelete(document, operation);
      break;
    case "SET_PROPERTY":
      applySetProperty(document, operation);
      break;
    case "MOVE_NODE":
      applyMove(document, operation);
      break;
    case "RESIZE_NODE":
      applyResize(document, operation);
      break;
    case "ROTATE_NODE":
      applyRotate(document, operation);
      break;
    case "REORDER_NODE":
      applyReorder(document, operation);
      break;
    case "REPARENT_NODE":
      applyReparent(document, operation);
      break;
    case "REPLACE_ASSET":
      applyReplaceAsset(document, operation);
      break;
    case "SET_TEXT":
      applySetText(document, operation);
      break;
    case "APPLY_STYLE":
      applyStyle(document, operation);
      break;
    case "BATCH":
      for (const child of nestedOperations(operation)) applyOne(document, child, expectedVersion, applied);
      break;
    default:
      throw failure(operation, "UNSUPPORTED_OPERATION", `Unsupported operation ${(operation as DesignOperation).type}`);
  }
  applied.push(operation.operation_id);
}

/**
 * Applies operations as one transaction. The input object is never mutated. Any failure returns the
 * original object and no document version is consumed. Constraint evaluation is intentionally NODE-39.
 */
export function executeOperations(
  document: DesignDocument,
  operations: readonly DesignOperation[],
): ExecutionResult {
  const previousVersion = getDocumentVersion(document);
  const working = cloneDocument(document);
  const applied: string[] = [];
  try {
    for (const operation of operations) applyOne(working, operation, previousVersion, applied);
    working.metadata.document_version = previousVersion + 1;
    return {
      ok: true,
      document: working as unknown as DesignDocument,
      applied_operation_ids: applied,
      previous_version: previousVersion,
      document_version: previousVersion + 1,
    };
  } catch (error) {
    const operationFailure: OperationFailure =
      error instanceof OperationError
        ? error.failure
        : {
            operation_id: "runtime",
            code: "INVALID_OPERATION",
            message: error instanceof Error ? error.message : "Unknown Design IR execution error",
          };
    return {
      ok: false,
      document,
      failures: [operationFailure],
      previous_version: previousVersion,
      document_version: previousVersion,
    };
  }
}

export function executeOperation(document: DesignDocument, operation: DesignOperation): ExecutionResult {
  return executeOperations(document, [operation]);
}

export function asDesignNode(value: unknown): DesignNode {
  return value as DesignNode;
}
