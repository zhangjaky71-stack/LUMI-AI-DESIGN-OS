import {
  DESIGN_NODE_KINDS,
  DESIGN_OPERATION_TYPES,
  IrRuntimeError,
  type DesignDocument,
  type DesignNode,
  type DesignOperation,
  type IrIssue,
} from "./types";

const SUPPORTED_SCHEMA_VERSIONS = new Set(["1.0", "1.1", "2.0"]);

function finiteWalk(value: unknown, pointer: string, issues: IrIssue[]): void {
  if (typeof value === "number" && !Number.isFinite(value)) {
    issues.push({
      code: "IR_SCHEMA_INVALID",
      message: "numeric values must be finite",
      pointer,
    });
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((child, index) => finiteWalk(child, `${pointer}/${index}`, issues));
    return;
  }
  if (value !== null && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      finiteWalk(
        child,
        `${pointer}/${key.replaceAll("~", "~0").replaceAll("/", "~1")}`,
        issues,
      );
    }
  }
}

function validateNode(
  id: string,
  node: DesignNode,
  document: DesignDocument,
  issues: IrIssue[],
): void {
  const pointer = `/nodes/${id}`;
  if (!id || node.id !== id) {
    issues.push({
      code: "IR_SCHEMA_INVALID",
      message: "node map key must equal node.id",
      pointer: `${pointer}/id`,
      node_ids: [id],
    });
  }
  const known = DESIGN_NODE_KINDS.includes(node.kind as (typeof DESIGN_NODE_KINDS)[number]);
  if (!known && !node.kind.startsWith("custom:")) {
    issues.push({
      code: "IR_SCHEMA_INVALID",
      message: `unsupported node kind ${node.kind}`,
      pointer: `${pointer}/kind`,
      node_ids: [id],
    });
  }
  if (!Array.isArray(node.children) || new Set(node.children).size !== node.children.length) {
    issues.push({
      code: "IR_SCHEMA_INVALID",
      message: "children must be a unique ordered array",
      pointer: `${pointer}/children`,
      node_ids: [id],
    });
  }
  if (node.parent_id !== null && !document.nodes[node.parent_id]) {
    issues.push({
      code: "IR_REFERENCE_MISSING",
      message: `parent ${node.parent_id} does not exist`,
      pointer: `${pointer}/parent_id`,
      node_ids: [id],
    });
  }
  for (const [index, childId] of node.children.entries()) {
    const child = document.nodes[childId];
    if (!child) {
      issues.push({
        code: "IR_REFERENCE_MISSING",
        message: `child ${childId} does not exist`,
        pointer: `${pointer}/children/${index}`,
        node_ids: [id, childId],
      });
    } else if (child.parent_id !== id) {
      issues.push({
        code: "IR_SCHEMA_INVALID",
        message: `child ${childId} parent_id must point to ${id}`,
        pointer: `${pointer}/children/${index}`,
        node_ids: [id, childId],
      });
    }
  }
}

function graphIssues(document: DesignDocument): IrIssue[] {
  const issues: IrIssue[] = [];
  const root = document.nodes[document.root_id];
  if (!root) return issues;
  if (root.parent_id !== null || root.kind !== "DOCUMENT_ROOT") {
    issues.push({
      code: "IR_SCHEMA_INVALID",
      message: "root node must be DOCUMENT_ROOT with parent_id=null",
      pointer: `/nodes/${document.root_id}`,
      node_ids: [document.root_id],
    });
  }

  const visiting = new Set<string>();
  const visited = new Set<string>();
  const walk = (id: string): void => {
    if (visiting.has(id)) {
      issues.push({
        code: "IR_GRAPH_CYCLE",
        message: `cycle detected at ${id}`,
        pointer: `/nodes/${id}`,
        node_ids: [id],
      });
      return;
    }
    if (visited.has(id)) return;
    const node = document.nodes[id];
    if (!node) return;
    visiting.add(id);
    for (const childId of node.children) walk(childId);
    visiting.delete(id);
    visited.add(id);
  };
  walk(document.root_id);
  for (const id of Object.keys(document.nodes)) {
    if (!visited.has(id)) {
      issues.push({
        code: "IR_REFERENCE_MISSING",
        message: `node ${id} is not reachable from root`,
        pointer: `/nodes/${id}`,
        node_ids: [id],
      });
    }
  }
  return issues;
}

export function validateDocument(document: DesignDocument): readonly IrIssue[] {
  const issues: IrIssue[] = [];
  if (!SUPPORTED_SCHEMA_VERSIONS.has(document.schema_version)) {
    issues.push({
      code: "IR_VERSION_UNSUPPORTED",
      message: `unsupported schema version ${document.schema_version}`,
      pointer: "/schema_version",
    });
  }
  if (!document.document_id || !document.root_id || !document.unit) {
    issues.push({
      code: "IR_SCHEMA_INVALID",
      message: "document_id, root_id and unit are required",
      pointer: "/",
    });
  }
  if (!document.nodes || typeof document.nodes !== "object" || Array.isArray(document.nodes)) {
    issues.push({ code: "IR_SCHEMA_INVALID", message: "nodes must be an object", pointer: "/nodes" });
    return issues;
  }
  if (!document.resources || typeof document.resources !== "object" || Array.isArray(document.resources)) {
    issues.push({
      code: "IR_SCHEMA_INVALID",
      message: "resources must be an object",
      pointer: "/resources",
    });
  }
  if (!document.metadata || typeof document.metadata !== "object" || Array.isArray(document.metadata)) {
    issues.push({
      code: "IR_SCHEMA_INVALID",
      message: "metadata must be an object",
      pointer: "/metadata",
    });
  }
  for (const [id, node] of Object.entries(document.nodes)) validateNode(id, node, document, issues);
  finiteWalk(document, "", issues);
  issues.push(...graphIssues(document));
  return issues;
}

export function parseDocument(raw: unknown): DesignDocument {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    throw new IrRuntimeError({ code: "IR_SCHEMA_INVALID", message: "document must be an object" });
  }
  const candidate = structuredClone(raw) as DesignDocument;
  const issues = validateDocument(candidate);
  if (issues.length) throw new IrRuntimeError(issues[0]!);
  return candidate;
}

export function validateOperation(operation: DesignOperation): void {
  if (
    !operation.operation_id ||
    !DESIGN_OPERATION_TYPES.includes(operation.type) ||
    !Number.isInteger(operation.expected_document_version) ||
    operation.expected_document_version < 0 ||
    !Array.isArray(operation.target_ids) ||
    operation.payload === null ||
    typeof operation.payload !== "object" ||
    Array.isArray(operation.payload)
  ) {
    throw new IrRuntimeError({
      code: "IR_OPERATION_INVALID",
      message: "operation envelope is invalid",
      operation_id: operation.operation_id,
    });
  }
  const finiteIssues: IrIssue[] = [];
  finiteWalk(operation.payload, "/payload", finiteIssues);
  if (finiteIssues.length) {
    throw new IrRuntimeError({
      ...finiteIssues[0]!,
      code: "IR_OPERATION_INVALID",
      operation_id: operation.operation_id,
    });
  }
}
