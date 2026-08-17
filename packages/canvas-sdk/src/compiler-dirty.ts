import { computeSemanticDiff, type DesignDocument, type SemanticDiff } from "../../design-ir/src/index";
import type { CompiledSceneSnapshot, ResourceInvalidation } from "./compiler-types";

function nodeIdFromProperty(value: string): string {
  const index = value.lastIndexOf(":");
  return index > 0 ? value.slice(0, index) : value;
}

function addDescendants(document: DesignDocument, id: string, target: Set<string>): void {
  const node = document.nodes[id];
  if (!node) return;
  for (const childId of node.children) {
    if (target.has(childId)) continue;
    target.add(childId);
    addDescendants(document, childId, target);
  }
}

function addAncestors(document: DesignDocument, id: string, target: Set<string>): void {
  let current = document.nodes[id]?.parent_id ?? null;
  while (current) {
    if (target.has(current)) break;
    target.add(current);
    current = document.nodes[current]?.parent_id ?? null;
  }
}

function referenceValue(node: DesignDocument["nodes"][string], key: string): string | undefined {
  const value = node?.[key];
  return typeof value === "string" ? value : undefined;
}

export function computeDirtyNodeIds(
  before: DesignDocument,
  after: DesignDocument,
  diff: SemanticDiff = computeSemanticDiff(before, after),
): readonly string[] {
  const dirty = new Set<string>();
  const seeds = [
    ...diff.nodes_added,
    ...diff.nodes_removed,
    ...diff.text_changed,
    ...diff.geometry_changed,
    ...diff.asset_replaced,
    ...diff.constraints_changed,
    ...diff.properties_changed.map(nodeIdFromProperty),
  ];
  for (const id of seeds) dirty.add(id);
  for (const id of [...dirty]) {
    addAncestors(before, id, dirty);
    addAncestors(after, id, dirty);
    const beforeNode = before.nodes[id];
    const afterNode = after.nodes[id];
    const inherited = [beforeNode, afterNode].some((node) => node?.kind === "GROUP" || node?.kind === "FRAME" || node?.kind === "COMPONENT");
    if (inherited || diff.geometry_changed.includes(id) || diff.nodes_added.includes(id)) {
      addDescendants(before, id, dirty);
      addDescendants(after, id, dirty);
    }
  }
  const referenced = new Set(dirty);
  for (const [id, node] of Object.entries(after.nodes)) {
    const maskId = referenceValue(node, "mask_id");
    const clipId = referenceValue(node, "clip_id");
    if ((maskId && referenced.has(maskId)) || (clipId && referenced.has(clipId))) dirty.add(id);
  }
  return [...dirty].sort();
}

function stringProp(node: DesignDocument["nodes"][string], key: string): string | undefined {
  const value = node?.[key];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

export function resourceInvalidationDirtyIds(
  document: DesignDocument,
  previous: CompiledSceneSnapshot,
  invalidation: ResourceInvalidation,
): readonly string[] {
  const assets = new Set(invalidation.assetIds ?? []);
  const fonts = new Set(invalidation.fontRefs ?? []);
  const styles = new Set(invalidation.styleRefs ?? []);
  const dirty = new Set<string>();
  for (const [id, node] of Object.entries(document.nodes)) {
    if (assets.has(stringProp(node, "asset_id") ?? "")) dirty.add(id);
    const fontRef = stringProp(node, "font_asset_id") ?? stringProp(node, "font_ref");
    if (fontRef && fonts.has(fontRef)) dirty.add(id);
    if ((node.style_refs ?? []).some((ref) => styles.has(ref))) dirty.add(id);
  }
  for (const id of previous.orderedIds) if (!document.nodes[id]) dirty.add(id);
  return [...dirty].sort();
}
