import type { DesignDocumentLike, DesignNodeLike, DesignOperationLike } from "./types";

export function projectOperation(
  document: DesignDocumentLike,
  operation: DesignOperationLike,
): DesignDocumentLike {
  const candidate = structuredClone(document) as DesignDocumentLike;
  const nodes = candidate.nodes as Record<string, DesignNodeLike>;
  const payload = operation.payload;
  if (operation.type === "CREATE_NODE") {
    const raw = payload.node;
    if (raw && typeof raw === "object" && !Array.isArray(raw)) {
      const node = structuredClone(raw) as DesignNodeLike;
      nodes[node.id] = node;
      if (node.parent_id) {
        const parent = nodes[node.parent_id];
        if (parent) {
          const children = [...parent.children];
          const rawIndex = payload.index;
          const index =
            typeof rawIndex === "number"
              ? Math.max(0, Math.min(rawIndex, children.length))
              : children.length;
          children.splice(index, 0, node.id);
          nodes[parent.id] = { ...parent, children };
        }
      }
    }
    return candidate;
  }
  for (const id of operation.target_ids) {
    const node = nodes[id];
    if (!node) continue;
    if (operation.type === "SET_PROPERTY" && typeof payload.property === "string") {
      nodes[id] = { ...node, [payload.property]: structuredClone(payload.value) };
    } else if (["MOVE_NODE", "RESIZE_NODE", "ROTATE_NODE"].includes(operation.type)) {
      const transform = { ...((node.transform as Record<string, unknown> | undefined) ?? {}) };
      if (operation.type === "MOVE_NODE") {
        transform.x = payload.x;
        transform.y = payload.y;
      } else if (operation.type === "RESIZE_NODE") {
        transform.width = payload.width;
        transform.height = payload.height;
      } else {
        transform.rotation_deg = payload.rotation_deg;
      }
      nodes[id] = { ...node, transform };
    } else if (operation.type === "REPLACE_ASSET") {
      nodes[id] = { ...node, asset_id: payload.asset_id };
    } else if (operation.type === "SET_TEXT") {
      nodes[id] = { ...node, content: payload.content };
    } else if (operation.type === "APPLY_STYLE") {
      nodes[id] = { ...node, style_refs: structuredClone(payload.style_refs) };
    }
  }
  return candidate;
}
