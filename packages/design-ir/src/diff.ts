import { canonicalStringify } from "./canonical";
import type { DesignDocument, DesignNode } from "./types";

export type SemanticChangeKind =
  | "NODE_ADDED"
  | "NODE_REMOVED"
  | "PROPERTY_CHANGED"
  | "GEOMETRY_CHANGED"
  | "ASSET_REPLACED"
  | "TEXT_CHANGED"
  | "CONSTRAINT_CHANGED"
  | "ORDER_CHANGED"
  | "PROVENANCE_CHANGED"
  | "SCHEMA_VERSION_CHANGED";

export interface SemanticChange {
  readonly kind: SemanticChangeKind;
  readonly node_id?: string;
  readonly property?: string;
  readonly before?: unknown;
  readonly after?: unknown;
}

export interface SemanticDiff {
  readonly changed: boolean;
  readonly changes: readonly SemanticChange[];
  readonly added_node_ids: readonly string[];
  readonly removed_node_ids: readonly string[];
  readonly changed_node_ids: readonly string[];
}

function equal(left: unknown, right: unknown): boolean {
  return canonicalStringify(left) === canonicalStringify(right);
}

function pushChange(
  changes: SemanticChange[],
  kind: SemanticChangeKind,
  nodeId: string | undefined,
  property: string | undefined,
  before: unknown,
  after: unknown,
): void {
  const base = { kind, before, after };
  changes.push({
    ...base,
    ...(nodeId ? { node_id: nodeId } : {}),
    ...(property ? { property } : {}),
  });
}

function compareNode(before: DesignNode, after: DesignNode, changes: SemanticChange[]): void {
  const id = before.id;
  if (!equal(before.transform, after.transform)) {
    pushChange(changes, "GEOMETRY_CHANGED", id, "transform", before.transform, after.transform);
  }
  if (!equal(before.children, after.children)) {
    pushChange(changes, "ORDER_CHANGED", id, "children", before.children, after.children);
  }
  if (!equal(before.constraint_refs, after.constraint_refs)) {
    pushChange(
      changes,
      "CONSTRAINT_CHANGED",
      id,
      "constraint_refs",
      before.constraint_refs,
      after.constraint_refs,
    );
  }
  if (!equal(before.asset_id, after.asset_id)) {
    pushChange(changes, "ASSET_REPLACED", id, "asset_id", before.asset_id, after.asset_id);
  }
  if (!equal(before.content, after.content)) {
    pushChange(changes, "TEXT_CHANGED", id, "content", before.content, after.content);
  }

  const specialized = new Set([
    "transform",
    "children",
    "constraint_refs",
    "asset_id",
    "content",
  ]);
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  for (const key of [...keys].sort()) {
    if (specialized.has(key) || key === "id") continue;
    if (!equal(before[key], after[key])) {
      pushChange(changes, "PROPERTY_CHANGED", id, key, before[key], after[key]);
    }
  }
}

export function semanticDiff(before: DesignDocument, after: DesignDocument): SemanticDiff {
  const changes: SemanticChange[] = [];
  const beforeIds = new Set(Object.keys(before.nodes));
  const afterIds = new Set(Object.keys(after.nodes));
  const added = [...afterIds].filter((id) => !beforeIds.has(id)).sort();
  const removed = [...beforeIds].filter((id) => !afterIds.has(id)).sort();

  for (const id of added) pushChange(changes, "NODE_ADDED", id, undefined, undefined, after.nodes[id]);
  for (const id of removed) pushChange(changes, "NODE_REMOVED", id, undefined, before.nodes[id], undefined);

  const changedIds: string[] = [];
  for (const id of [...beforeIds].filter((value) => afterIds.has(value)).sort()) {
    const left = before.nodes[id];
    const right = after.nodes[id];
    if (!left || !right || equal(left, right)) continue;
    changedIds.push(id);
    compareNode(left, right, changes);
  }

  if (before.schema_version !== after.schema_version) {
    pushChange(
      changes,
      "SCHEMA_VERSION_CHANGED",
      undefined,
      "schema_version",
      before.schema_version,
      after.schema_version,
    );
  }

  const beforeProvenance = before.metadata.provenance;
  const afterProvenance = after.metadata.provenance;
  if (!equal(beforeProvenance, afterProvenance)) {
    pushChange(
      changes,
      "PROVENANCE_CHANGED",
      undefined,
      "metadata.provenance",
      beforeProvenance,
      afterProvenance,
    );
  }

  return {
    changed: changes.length > 0,
    changes,
    added_node_ids: added,
    removed_node_ids: removed,
    changed_node_ids: changedIds,
  };
}
