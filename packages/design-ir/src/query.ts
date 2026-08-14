import type { DesignDocument, DesignNode, DesignTransform } from "./types";

export interface NodeSelector {
  readonly ids?: readonly string[];
  readonly roles?: readonly string[];
  readonly kinds?: readonly string[];
  readonly parent_id?: string;
  readonly brand_binding?: string;
  readonly asset_binding?: string;
  readonly locked?: boolean;
}

export interface SpatialBounds {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface SpatialIndexAdapter {
  rebuild(entries: readonly { readonly node_id: string; readonly bounds: SpatialBounds }[]): void;
  search(bounds: SpatialBounds): readonly string[];
}

function contains(values: readonly string[] | undefined, value: string | undefined): boolean {
  return values === undefined || (value !== undefined && values.includes(value));
}

function metadataString(node: DesignNode, key: string): string | undefined {
  const value = node.metadata?.[key];
  return typeof value === "string" ? value : undefined;
}

export function queryNodes(document: DesignDocument, selector: NodeSelector): readonly DesignNode[] {
  const idSet = selector.ids ? new Set(selector.ids) : undefined;
  return Object.values(document.nodes).filter((node) => {
    if (idSet && !idSet.has(node.id)) return false;
    if (!contains(selector.roles, node.role)) return false;
    if (!contains(selector.kinds, node.kind)) return false;
    if (selector.parent_id !== undefined && node.parent_id !== selector.parent_id) return false;
    if (selector.locked !== undefined && Boolean(node.locked) !== selector.locked) return false;
    if (
      selector.brand_binding !== undefined &&
      metadataString(node, "brand_binding") !== selector.brand_binding
    ) {
      return false;
    }
    if (
      selector.asset_binding !== undefined &&
      node.asset_id !== selector.asset_binding &&
      metadataString(node, "asset_binding") !== selector.asset_binding
    ) {
      return false;
    }
    return true;
  });
}

export function boundsFromTransform(transform: DesignTransform | undefined): SpatialBounds | undefined {
  if (!transform) return undefined;
  const { x, y, width, height } = transform;
  if (
    typeof x !== "number" ||
    typeof y !== "number" ||
    typeof width !== "number" ||
    typeof height !== "number" ||
    ![x, y, width, height].every(Number.isFinite)
  ) {
    return undefined;
  }
  return { x, y, width, height };
}

export function buildSpatialEntries(
  document: DesignDocument,
): readonly { readonly node_id: string; readonly bounds: SpatialBounds }[] {
  return Object.values(document.nodes)
    .map((node) => {
      const bounds = boundsFromTransform(node.transform);
      return bounds ? { node_id: node.id, bounds } : undefined;
    })
    .filter(
      (entry): entry is { readonly node_id: string; readonly bounds: SpatialBounds } =>
        entry !== undefined,
    );
}
