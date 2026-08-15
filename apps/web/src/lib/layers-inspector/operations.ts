import type { DesignDocument, DesignNode, DesignOperation } from "@lumi/design-ir";
import { getDocumentVersion } from "@lumi/design-ir";
import type { InspectorTextPatch, InspectorTransformPatch } from "./types";

function finite(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function operation(
  document: DesignDocument,
  type: DesignOperation["type"],
  targetIds: readonly string[],
  payload: Readonly<Record<string, unknown>>,
  reason: string,
): DesignOperation {
  return {
    operation_id: `${reason}-${crypto.randomUUID()}`,
    type,
    target_ids: [...targetIds],
    expected_document_version: getDocumentVersion(document),
    payload,
    reason,
  };
}

export function propertyOperation(
  document: DesignDocument,
  nodeIds: readonly string[],
  path: string,
  value: unknown,
  reason: string,
): DesignOperation {
  return operation(document, "SET_PROPERTY", nodeIds, { path, value }, reason);
}

export function renameOperation(
  document: DesignDocument,
  nodeId: string,
  name: string,
): DesignOperation {
  return propertyOperation(document, [nodeId], "name", name.trim(), "inspector-rename");
}

export function transformOperations(
  document: DesignDocument,
  nodeId: string,
  patch: InspectorTransformPatch,
): DesignOperation[] {
  const node = document.nodes[nodeId];
  if (!node) return [];
  const current = node.transform ?? {};
  const operations: DesignOperation[] = [];
  if (patch.x !== undefined || patch.y !== undefined) {
    operations.push(
      operation(
        document,
        "MOVE_NODE",
        [nodeId],
        {
          x: patch.x ?? finite(current.x),
          y: patch.y ?? finite(current.y),
        },
        "inspector-move",
      ),
    );
  }
  if (patch.width !== undefined || patch.height !== undefined) {
    operations.push(
      operation(
        document,
        "RESIZE_NODE",
        [nodeId],
        {
          width: Math.max(0, patch.width ?? finite(current.width)),
          height: Math.max(0, patch.height ?? finite(current.height)),
        },
        "inspector-resize",
      ),
    );
  }
  if (patch.rotation_deg !== undefined) {
    operations.push(
      operation(
        document,
        "ROTATE_NODE",
        [nodeId],
        { rotation_deg: patch.rotation_deg },
        "inspector-rotate",
      ),
    );
  }
  return operations;
}

export function textOperations(
  document: DesignDocument,
  nodeId: string,
  patch: InspectorTextPatch,
): DesignOperation[] {
  const node = document.nodes[nodeId];
  if (!node || node.kind !== "TEXT") return [];
  const result: DesignOperation[] = [];
  if (patch.content !== undefined) {
    result.push(operation(document, "SET_TEXT", [nodeId], { content: patch.content }, "inspector-text"));
  }
  const metadataEntries: readonly [keyof Omit<InspectorTextPatch, "content">, unknown][] = [
    ["font_size", patch.font_size],
    ["line_height", patch.line_height],
    ["letter_spacing", patch.letter_spacing],
    ["text_align", patch.text_align],
    ["fill", patch.fill],
  ];
  for (const [key, value] of metadataEntries) {
    if (value !== undefined) {
      result.push(propertyOperation(document, [nodeId], `metadata.${key}`, value, `inspector-text-${key}`));
    }
  }
  return result;
}

export function moveLayerOperation(
  document: DesignDocument,
  nodeId: string,
  direction: "up" | "down",
): DesignOperation | null {
  const node = document.nodes[nodeId];
  if (!node?.parent_id) return null;
  const siblings = document.nodes[node.parent_id]?.children ?? [];
  const index = siblings.indexOf(nodeId);
  if (index < 0) return null;
  const nextIndex = direction === "up" ? Math.min(siblings.length - 1, index + 1) : Math.max(0, index - 1);
  if (nextIndex === index) return null;
  return operation(document, "REORDER_NODE", [nodeId], { index: nextIndex }, `layers-${direction}`);
}

function selectionBounds(nodes: readonly DesignNode[]): { x: number; y: number; width: number; height: number } {
  const x = Math.min(...nodes.map((node) => finite(node.transform?.x)));
  const y = Math.min(...nodes.map((node) => finite(node.transform?.y)));
  const right = Math.max(...nodes.map((node) => finite(node.transform?.x) + Math.max(0, finite(node.transform?.width))));
  const bottom = Math.max(...nodes.map((node) => finite(node.transform?.y) + Math.max(0, finite(node.transform?.height))));
  return { x, y, width: Math.max(0, right - x), height: Math.max(0, bottom - y) };
}

export interface GroupOperationsResult {
  readonly group_id: string;
  readonly operations: readonly DesignOperation[];
}

export function groupOperations(
  document: DesignDocument,
  selectedIds: readonly string[],
): GroupOperationsResult | null {
  if (selectedIds.length < 2) return null;
  const nodes = selectedIds.map((id) => document.nodes[id]).filter((node): node is DesignNode => Boolean(node));
  if (nodes.length !== selectedIds.length) return null;
  const parentId = nodes[0]?.parent_id ?? null;
  if (!parentId || nodes.some((node) => node.parent_id !== parentId || node.locked)) return null;
  const parent = document.nodes[parentId];
  if (!parent) return null;
  const siblings = parent.children;
  const indexes = nodes.map((node) => siblings.indexOf(node.id)).filter((index) => index >= 0);
  if (indexes.length !== nodes.length) return null;
  const bounds = selectionBounds(nodes);
  const groupId = `group-${crypto.randomUUID().slice(0, 12)}`;
  const create = operation(
    document,
    "CREATE_NODE",
    [groupId],
    {
      parent_id: parentId,
      index: Math.min(...indexes),
      node: {
        id: groupId,
        kind: "GROUP",
        name: "Group",
        parent_id: parentId,
        children: [],
        transform: bounds,
      },
    },
    "layers-group-create",
  );
  const operations: DesignOperation[] = [create];
  nodes.forEach((node, index) => {
    operations.push(
      operation(
        document,
        "MOVE_NODE",
        [node.id],
        {
          x: finite(node.transform?.x) - bounds.x,
          y: finite(node.transform?.y) - bounds.y,
        },
        "layers-group-localize",
      ),
      operation(
        document,
        "REPARENT_NODE",
        [node.id],
        { parent_id: groupId, index },
        "layers-group-reparent",
      ),
    );
  });
  return { group_id: groupId, operations };
}

export interface UngroupOperationsResult {
  readonly selected_ids: readonly string[];
  readonly operations: readonly DesignOperation[];
}

export function ungroupOperations(
  document: DesignDocument,
  groupId: string,
): UngroupOperationsResult | null {
  const group = document.nodes[groupId];
  if (!group || group.kind !== "GROUP" || !group.parent_id || group.locked) return null;
  if (finite(group.transform?.rotation_deg) !== 0) return null;
  const parent = document.nodes[group.parent_id];
  if (!parent) return null;
  const groupIndex = parent.children.indexOf(groupId);
  if (groupIndex < 0) return null;
  const groupX = finite(group.transform?.x);
  const groupY = finite(group.transform?.y);
  const childIds = [...group.children];
  const operations: DesignOperation[] = [];
  childIds.forEach((childId, index) => {
    const child = document.nodes[childId];
    if (!child) return;
    operations.push(
      operation(
        document,
        "MOVE_NODE",
        [childId],
        {
          x: groupX + finite(child.transform?.x),
          y: groupY + finite(child.transform?.y),
        },
        "layers-ungroup-globalize",
      ),
      operation(
        document,
        "REPARENT_NODE",
        [childId],
        { parent_id: group.parent_id, index: groupIndex + index },
        "layers-ungroup-reparent",
      ),
    );
  });
  operations.push(operation(document, "DELETE_NODE", [groupId], {}, "layers-ungroup-delete"));
  return { selected_ids: childIds, operations };
}
