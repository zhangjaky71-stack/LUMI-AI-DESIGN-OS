import {
  canonicalStringify,
  semanticDiff,
  type DesignDocument,
  type SemanticChange,
  type SemanticDiff,
} from "../../design-ir/src/index";

export interface CompilerDirtyPlan {
  readonly dirty_node_ids: readonly string[];
  readonly removed_node_ids: readonly string[];
  readonly resource_ids: readonly string[];
  readonly requires_full_compile: boolean;
  readonly reason?: string;
}

function descendants(document: DesignDocument, id: string, result: Set<string>): void {
  const node = document.nodes[id];
  if (!node) return;
  for (const childId of node.children) {
    if (result.has(childId)) continue;
    result.add(childId);
    descendants(document, childId, result);
  }
}

function ancestors(document: DesignDocument, id: string, result: Set<string>): void {
  let current = document.nodes[id]?.parent_id ?? null;
  const seen = new Set<string>();
  while (current && !seen.has(current)) {
    seen.add(current);
    result.add(current);
    current = document.nodes[current]?.parent_id ?? null;
  }
}

function changedResources(before: DesignDocument, after: DesignDocument): string[] {
  const keys = new Set([...Object.keys(before.resources), ...Object.keys(after.resources)]);
  return [...keys]
    .filter(
      (key) =>
        canonicalStringify(before.resources[key]) !== canonicalStringify(after.resources[key]),
    )
    .sort();
}

function fontRef(document: DesignDocument, nodeId: string): string | null {
  const node = document.nodes[nodeId];
  const metadata = node?.metadata ?? {};
  const value = metadata.font_asset_id ?? metadata.font_ref;
  return typeof value === "string" && value.length > 0 ? value : null;
}

function nodeDependsOnResource(
  document: DesignDocument,
  nodeId: string,
  resourceIds: ReadonlySet<string>,
): boolean {
  const node = document.nodes[nodeId];
  if (!node) return false;
  if (typeof node.asset_id === "string" && resourceIds.has(node.asset_id)) return true;
  if ((node.style_refs ?? []).some((ref) => resourceIds.has(ref))) return true;
  const font = fontRef(document, nodeId);
  return font ? resourceIds.has(font) : false;
}

function changeAffectsDescendants(change: SemanticChange): boolean {
  if (change.kind === "GEOMETRY_CHANGED") return true;
  if (change.kind === "ORDER_CHANGED") return true;
  if (change.kind === "NODE_ADDED" || change.kind === "NODE_REMOVED") return true;
  if (change.kind !== "PROPERTY_CHANGED") return false;
  return ["parent_id", "visible", "locked", "style_refs", "opacity", "blend_mode"].includes(
    change.property ?? "",
  );
}

export function planCompilerDirtyNodes(
  before: DesignDocument,
  after: DesignDocument,
  suppliedDiff?: SemanticDiff,
): CompilerDirtyPlan {
  const diff = suppliedDiff ?? semanticDiff(before, after);
  if (!diff.changed) {
    return {
      dirty_node_ids: [],
      removed_node_ids: [],
      resource_ids: [],
      requires_full_compile: false,
    };
  }

  const schemaChanged = diff.changes.some((change) => change.kind === "SCHEMA_VERSION_CHANGED");
  const rootChanged = before.root_id !== after.root_id;
  if (schemaChanged || rootChanged) {
    return {
      dirty_node_ids: Object.keys(after.nodes).sort(),
      removed_node_ids: [...diff.removed_node_ids],
      resource_ids: changedResources(before, after),
      requires_full_compile: true,
      reason: schemaChanged ? "schema-version-changed" : "root-changed",
    };
  }

  const dirty = new Set<string>([...diff.added_node_ids, ...diff.changed_node_ids]);
  const removed = new Set(diff.removed_node_ids);

  for (const change of diff.changes) {
    const id = change.node_id;
    if (!id) continue;
    if (after.nodes[id]) dirty.add(id);
    if (changeAffectsDescendants(change) && after.nodes[id]) descendants(after, id, dirty);
    if (change.kind === "ORDER_CHANGED" || change.kind === "NODE_ADDED" || change.kind === "NODE_REMOVED") {
      if (after.nodes[id]) ancestors(after, id, dirty);
      if (before.nodes[id]) ancestors(before, id, dirty);
    }
  }

  for (const removedId of removed) {
    const parent = before.nodes[removedId]?.parent_id;
    if (parent && after.nodes[parent]) dirty.add(parent);
  }

  const resources = changedResources(before, after);
  if (resources.length) {
    const resourceSet = new Set(resources);
    for (const id of Object.keys(after.nodes)) {
      if (nodeDependsOnResource(after, id, resourceSet)) dirty.add(id);
    }
  }

  return {
    dirty_node_ids: [...dirty].filter((id) => Boolean(after.nodes[id])).sort(),
    removed_node_ids: [...removed].sort(),
    resource_ids: resources,
    requires_full_compile: false,
  };
}
