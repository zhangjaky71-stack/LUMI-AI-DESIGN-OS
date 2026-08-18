import type { DesignDocument, DesignNode } from "@lumi/design-ir";

export const LAYER_ROW_HEIGHT = 30;
export const LAYER_OVERSCAN = 8;

export type LayerRow = {
  id: string;
  node: DesignNode;
  depth: number;
  expandable: boolean;
  expanded: boolean;
  matched: boolean;
};

export type VirtualLayerWindow = {
  rows: readonly LayerRow[];
  start: number;
  end: number;
  offset: number;
  totalHeight: number;
};

export type ConstraintBadge = {
  id: string;
  type: string;
  severity: "HARD" | "SOFT" | "ADVISORY" | "UNKNOWN";
  source: string;
  reason: string;
};

export type BrandBinding = {
  property: string;
  tokenRef: string;
};

export function flattenLayerRows(
  document: DesignDocument,
  collapsed: ReadonlySet<string>,
  query = "",
): LayerRow[] {
  const normalized = query.trim().toLocaleLowerCase();
  const keep = normalized ? matchingWithAncestors(document, normalized) : null;
  const rows: LayerRow[] = [];
  const visited = new Set<string>();

  const visit = (id: string, depth: number): void => {
    if (visited.has(id)) return;
    visited.add(id);
    const node = document.nodes[id];
    if (!node) return;
    if (node.kind !== "DOCUMENT_ROOT" && (!keep || keep.has(id))) {
      const expandable = node.children.length > 0;
      rows.push({
        id,
        node,
        depth,
        expandable,
        expanded: expandable && !collapsed.has(id),
        matched: normalized ? matches(node, normalized) : false,
      });
    }
    if (node.kind !== "DOCUMENT_ROOT" && collapsed.has(id) && !normalized) return;
    for (const childId of node.children) visit(childId, node.kind === "DOCUMENT_ROOT" ? depth : depth + 1);
  };

  visit(document.root_id, 0);
  return rows;
}

export function virtualLayerWindow(
  rows: readonly LayerRow[],
  scrollTop: number,
  viewportHeight: number,
  rowHeight = LAYER_ROW_HEIGHT,
  overscan = LAYER_OVERSCAN,
): VirtualLayerWindow {
  const safeHeight = Math.max(rowHeight, viewportHeight);
  const visibleStart = Math.max(0, Math.floor(Math.max(0, scrollTop) / rowHeight));
  const visibleCount = Math.ceil(safeHeight / rowHeight);
  const start = Math.max(0, visibleStart - overscan);
  const end = Math.min(rows.length, visibleStart + visibleCount + overscan);
  return {
    rows: rows.slice(start, end),
    start,
    end,
    offset: start * rowHeight,
    totalHeight: rows.length * rowHeight,
  };
}

export function commonValue<T>(
  nodes: readonly DesignNode[],
  read: (node: DesignNode) => T,
): { mixed: boolean; value: T | undefined } {
  if (!nodes.length) return { mixed: false, value: undefined };
  const first = read(nodes[0]!);
  for (let index = 1; index < nodes.length; index += 1) {
    if (!deepEqual(first, read(nodes[index]!))) return { mixed: true, value: undefined };
  }
  return { mixed: false, value: first };
}

export function constraintBadges(node: DesignNode): ConstraintBadge[] {
  const metadata = record(node.metadata);
  const raw = metadata?.constraint_summary;
  const badges: ConstraintBadge[] = [];
  if (Array.isArray(raw)) {
    raw.forEach((entry, index) => {
      const item = record(entry);
      if (!item) return;
      badges.push({
        id: stringValue(item.id) ?? `constraint-${index}`,
        type: stringValue(item.type) ?? "CONSTRAINT",
        severity: severity(item.severity),
        source: stringValue(item.source) ?? "UNRESOLVED",
        reason: stringValue(item.reason) ?? "Constraint details are enforced by the server runtime.",
      });
    });
  }
  if (node.locked === true && !badges.some((item) => item.type.startsWith("LOCK"))) {
    badges.unshift({
      id: `persisted-lock:${node.id}`,
      type: "LOCKED_NODE",
      severity: "HARD",
      source: "UNRESOLVED",
      reason: "This lock is persisted in Design IR. Its originating constraint source is not projected to the browser.",
    });
  }
  return badges;
}

export function brandBindings(node: DesignNode): BrandBinding[] {
  const values: BrandBinding[] = [];
  const fill = record(node.fill);
  const fillToken = stringValue(fill?.token_ref);
  if (fillToken) values.push({ property: "Fill", tokenRef: fillToken });
  const stroke = record(node.stroke);
  const paint = record(stroke?.paint);
  const strokeToken = stringValue(paint?.token_ref);
  if (strokeToken) values.push({ property: "Stroke", tokenRef: strokeToken });
  const metadata = record(node.metadata);
  const explicit = record(metadata?.brand_bindings);
  if (explicit) {
    for (const [property, value] of Object.entries(explicit)) {
      const tokenRef = stringValue(value);
      if (tokenRef && !values.some((item) => item.property === property && item.tokenRef === tokenRef)) {
        values.push({ property, tokenRef });
      }
    }
  }
  return values;
}

export function layerLabel(node: DesignNode): string {
  const name = typeof node.name === "string" ? node.name.trim() : "";
  if (name) return name;
  const role = typeof node.role === "string" ? node.role.trim() : "";
  return role || node.kind;
}

function matchingWithAncestors(document: DesignDocument, query: string): Set<string> {
  const keep = new Set<string>();
  for (const node of Object.values(document.nodes)) {
    if (!matches(node, query)) continue;
    let current: DesignNode | undefined = node;
    const seen = new Set<string>();
    while (current && !seen.has(current.id)) {
      seen.add(current.id);
      keep.add(current.id);
      current = current.parent_id ? document.nodes[current.parent_id] : undefined;
    }
  }
  return keep;
}

function matches(node: DesignNode, query: string): boolean {
  const haystack = [node.name, node.role, node.kind, node.id, ...(semanticTags(node))]
    .filter((value): value is string => typeof value === "string")
    .join(" ")
    .toLocaleLowerCase();
  return haystack.includes(query);
}

function semanticTags(node: DesignNode): string[] {
  const semantic = record(node.semantic);
  const tags = semantic?.tags;
  return Array.isArray(tags) ? tags.filter((item): item is string => typeof item === "string") : [];
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function severity(value: unknown): ConstraintBadge["severity"] {
  return value === "HARD" || value === "SOFT" || value === "ADVISORY" ? value : "UNKNOWN";
}

function deepEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  try {
    return JSON.stringify(left) === JSON.stringify(right);
  } catch {
    return false;
  }
}