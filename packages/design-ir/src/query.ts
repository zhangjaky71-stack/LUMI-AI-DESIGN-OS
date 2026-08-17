import type { DesignDocument, DesignNode, NodeSelector } from "./types";

function hasBinding(node: DesignNode, key: string, expected: string): boolean {
  const direct = node[key];
  if (typeof direct === "string") return direct === expected;
  const semantic = node.semantic?.[key];
  return typeof semantic === "string" && semantic === expected;
}

function descendantOf(document: DesignDocument, node: DesignNode, ancestorId: string): boolean {
  let current = node.parent_id;
  while (current !== null) {
    if (current === ancestorId) return true;
    current = document.nodes[current]?.parent_id ?? null;
  }
  return false;
}

export function queryNodes(document: DesignDocument, selector: NodeSelector): readonly DesignNode[] {
  if (selector.id) {
    const node = document.nodes[selector.id];
    return node ? [node] : [];
  }
  return Object.values(document.nodes).filter((node) => {
    if (selector.role !== undefined && node.role !== selector.role) return false;
    if (selector.kind !== undefined && node.kind !== selector.kind) return false;
    if (selector.parent_id !== undefined && node.parent_id !== selector.parent_id) return false;
    if (selector.locked !== undefined && Boolean(node.locked) !== selector.locked) return false;
    if (
      selector.brand_binding !== undefined &&
      !hasBinding(node, "brand_binding", selector.brand_binding)
    ) return false;
    if (
      selector.asset_binding !== undefined &&
      !hasBinding(node, "asset_id", selector.asset_binding)
    ) return false;
    if (
      selector.frame_id !== undefined &&
      node.id !== selector.frame_id &&
      !descendantOf(document, node, selector.frame_id)
    ) return false;
    return true;
  });
}
