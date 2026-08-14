import { DESIGN_NODE_KINDS, type DesignDocument, type DesignNode } from "./types";

export type IrValidationCode =
  | "IR_SCHEMA_INVALID"
  | "IR_GRAPH_CYCLE"
  | "IR_REFERENCE_MISSING"
  | "IR_VERSION_UNSUPPORTED";

export interface IrValidationIssue {
  readonly code: IrValidationCode;
  readonly message: string;
  readonly pointer: string;
  readonly node_id?: string;
}

export interface IrValidationResult {
  readonly valid: boolean;
  readonly issues: readonly IrValidationIssue[];
}

const SUPPORTED_SCHEMA_MAJOR = "1";

function issue(
  issues: IrValidationIssue[],
  code: IrValidationCode,
  message: string,
  pointer: string,
  nodeId?: string,
): void {
  issues.push({ code, message, pointer, ...(nodeId ? { node_id: nodeId } : {}) });
}

function finiteWalk(value: unknown, pointer: string, issues: IrValidationIssue[]): void {
  if (typeof value === "number" && !Number.isFinite(value)) {
    issue(issues, "IR_SCHEMA_INVALID", "Numeric values must be finite", pointer);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((child, index) => finiteWalk(child, `${pointer}/${index}`, issues));
  } else if (value !== null && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      finiteWalk(child, `${pointer}/${key.replaceAll("~", "~0").replaceAll("/", "~1")}`, issues);
    }
  }
}

function validateNode(
  id: string,
  node: DesignNode,
  document: DesignDocument,
  issues: IrValidationIssue[],
): void {
  const pointer = `/nodes/${id}`;
  if (node.id !== id) issue(issues, "IR_SCHEMA_INVALID", "Node map key must equal node.id", `${pointer}/id`, id);
  if (!DESIGN_NODE_KINDS.includes(node.kind as (typeof DESIGN_NODE_KINDS)[number]) && !node.kind.startsWith("custom:")) {
    issue(issues, "IR_SCHEMA_INVALID", `Unsupported node kind ${node.kind}`, `${pointer}/kind`, id);
  }
  if (!Array.isArray(node.children)) issue(issues, "IR_SCHEMA_INVALID", "children must be an array", `${pointer}/children`, id);
  if (node.parent_id !== null && !document.nodes[node.parent_id]) {
    issue(issues, "IR_REFERENCE_MISSING", `Parent ${node.parent_id} does not exist`, `${pointer}/parent_id`, id);
  }
  node.children.forEach((childId, index) => {
    const child = document.nodes[childId];
    if (!child) {
      issue(issues, "IR_REFERENCE_MISSING", `Child ${childId} does not exist`, `${pointer}/children/${index}`, id);
    } else if (child.parent_id !== id) {
      issue(
        issues,
        "IR_SCHEMA_INVALID",
        `Child ${childId} parent_id must point back to ${id}`,
        `${pointer}/children/${index}`,
        id,
      );
    }
  });
}

function detectCycles(document: DesignDocument, issues: IrValidationIssue[]): void {
  const visiting = new Set<string>();
  const visited = new Set<string>();
  const walk = (id: string): void => {
    if (visiting.has(id)) {
      issue(issues, "IR_GRAPH_CYCLE", `Cycle detected at ${id}`, `/nodes/${id}`, id);
      return;
    }
    if (visited.has(id)) return;
    const node = document.nodes[id];
    if (!node) return;
    visiting.add(id);
    node.children.forEach(walk);
    visiting.delete(id);
    visited.add(id);
  };
  walk(document.root_id);
}

export function validateDocument(document: DesignDocument): IrValidationResult {
  const issues: IrValidationIssue[] = [];
  const major = document.schema_version.split(".")[0];
  if (major !== SUPPORTED_SCHEMA_MAJOR) {
    issue(
      issues,
      "IR_VERSION_UNSUPPORTED",
      `Unsupported Design IR major version ${document.schema_version}`,
      "/schema_version",
    );
  }
  if (!document.document_id) issue(issues, "IR_SCHEMA_INVALID", "document_id is required", "/document_id");
  if (!document.root_id || !document.nodes[document.root_id]) {
    issue(issues, "IR_REFERENCE_MISSING", "root_id must reference an existing node", "/root_id");
  }
  for (const [id, node] of Object.entries(document.nodes)) validateNode(id, node, document, issues);
  finiteWalk(document, "", issues);
  detectCycles(document, issues);
  return { valid: issues.length === 0, issues };
}

export function parseDocument(raw: unknown): DesignDocument {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("IR_SCHEMA_INVALID: document must be an object");
  }
  const candidate = structuredClone(raw) as DesignDocument;
  if (
    typeof candidate.schema_version !== "string" ||
    typeof candidate.document_id !== "string" ||
    typeof candidate.root_id !== "string" ||
    candidate.nodes === null ||
    typeof candidate.nodes !== "object" ||
    candidate.resources === null ||
    typeof candidate.resources !== "object" ||
    candidate.metadata === null ||
    typeof candidate.metadata !== "object"
  ) {
    throw new Error("IR_SCHEMA_INVALID: required Design IR fields are missing or invalid");
  }
  const result = validateDocument(candidate);
  if (!result.valid) {
    const first = result.issues[0]!;
    throw new Error(`${first.code}: ${first.pointer} ${first.message}`);
  }
  return candidate;
}
