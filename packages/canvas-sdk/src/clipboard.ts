import {
  getDocumentVersion,
  type DesignDocument,
  type DesignNode,
  type DesignOperation,
} from "../../design-ir/src/index";

export interface CanvasClipboardFragment {
  readonly format: "lumi-design-ir-fragment-v1";
  readonly source_document_id: string;
  readonly root_node_ids: readonly string[];
  readonly nodes: Readonly<Record<string, DesignNode>>;
  readonly asset_ids: readonly string[];
}

export interface ClipboardAssetPolicy {
  mapAssetId(
    assetId: string,
    sourceDocumentId: string,
    targetDocumentId: string,
  ): string | null;
}

function descendants(document: DesignDocument, id: string, result: Set<string>): void {
  if (result.has(id)) return;
  const node = document.nodes[id];
  if (!node) return;
  result.add(id);
  for (const childId of node.children) descendants(document, childId, result);
}

function sanitizeNode(node: DesignNode): DesignNode {
  const metadata = Object.fromEntries(
    Object.entries(node.metadata ?? {}).filter(
      ([key]) =>
        !key.startsWith("runtime:") &&
        !key.startsWith("pixi:") &&
        !key.startsWith("ephemeral:"),
    ),
  );
  return { ...structuredClone(node), metadata };
}

export function createClipboardFragment(
  document: DesignDocument,
  selectedIds: readonly string[],
): CanvasClipboardFragment {
  const included = new Set<string>();
  for (const id of selectedIds) descendants(document, id, included);
  const nodes: Record<string, DesignNode> = {};
  const assetIds = new Set<string>();
  for (const id of included) {
    const node = document.nodes[id];
    if (!node) continue;
    nodes[id] = sanitizeNode(node);
    if (typeof node.asset_id === "string") assetIds.add(node.asset_id);
  }
  return {
    format: "lumi-design-ir-fragment-v1",
    source_document_id: document.document_id,
    root_node_ids: selectedIds.filter((id) => included.has(id)),
    nodes,
    asset_ids: [...assetIds].sort(),
  };
}

export function serializeClipboardFragment(fragment: CanvasClipboardFragment): string {
  return JSON.stringify(fragment);
}

export function parseClipboardFragment(value: string): CanvasClipboardFragment | null {
  try {
    const parsed = JSON.parse(value) as Partial<CanvasClipboardFragment>;
    if (
      parsed.format !== "lumi-design-ir-fragment-v1" ||
      typeof parsed.source_document_id !== "string" ||
      !Array.isArray(parsed.root_node_ids) ||
      !parsed.nodes ||
      typeof parsed.nodes !== "object"
    ) {
      return null;
    }
    return parsed as CanvasClipboardFragment;
  } catch {
    return null;
  }
}

export function buildPasteOperations(
  fragment: CanvasClipboardFragment,
  targetDocument: DesignDocument,
  parentId: string,
  operationPrefix: string,
  assetPolicy: ClipboardAssetPolicy,
  offset = 24,
): DesignOperation[] {
  if (!targetDocument.nodes[parentId]) {
    throw new Error(`paste parent not found: ${parentId}`);
  }
  const version = getDocumentVersion(targetDocument);
  const idMap = new Map<string, string>();
  const taken = new Set(Object.keys(targetDocument.nodes));
  const allocate = (sourceId: string): string => {
    let suffix = 1;
    let candidate = `${sourceId}-copy-${suffix}`;
    while (taken.has(candidate)) {
      suffix += 1;
      candidate = `${sourceId}-copy-${suffix}`;
    }
    taken.add(candidate);
    idMap.set(sourceId, candidate);
    return candidate;
  };
  for (const id of Object.keys(fragment.nodes).sort()) allocate(id);

  const depth = (id: string): number => {
    let current = fragment.nodes[id];
    let value = 0;
    const seen = new Set<string>();
    while (
      current?.parent_id &&
      fragment.nodes[current.parent_id] &&
      !seen.has(current.parent_id)
    ) {
      seen.add(current.parent_id);
      value += 1;
      current = fragment.nodes[current.parent_id];
    }
    return value;
  };

  const ordered = Object.keys(fragment.nodes).sort(
    (left, right) => depth(left) - depth(right) || left.localeCompare(right),
  );
  const operations: DesignOperation[] = [];
  let index = 0;
  for (const sourceId of ordered) {
    const source = fragment.nodes[sourceId];
    const nextId = idMap.get(sourceId);
    if (!source || !nextId) continue;
    const isFragmentRoot = fragment.root_node_ids.includes(sourceId);
    const sourceParentId = source.parent_id;
    const mappedParent = sourceParentId ? idMap.get(sourceParentId) : undefined;
    const nextParentId = isFragmentRoot ? parentId : (mappedParent ?? parentId);
    const mappedAsset =
      typeof source.asset_id === "string"
        ? assetPolicy.mapAssetId(
            source.asset_id,
            fragment.source_document_id,
            targetDocument.document_id,
          )
        : null;
    const transform = {
      ...(source.transform ?? {}),
      ...(isFragmentRoot
        ? {
            x: (source.transform?.x ?? 0) + offset,
            y: (source.transform?.y ?? 0) + offset,
          }
        : {}),
    };
    const node: DesignNode = {
      ...structuredClone(source),
      id: nextId,
      parent_id: nextParentId,
      children: source.children
        .map((childId) => idMap.get(childId))
        .filter((id): id is string => Boolean(id)),
      transform,
      ...(typeof source.asset_id === "string"
        ? mappedAsset
          ? { asset_id: mappedAsset }
          : {
              asset_id: source.asset_id,
              metadata: {
                ...(source.metadata ?? {}),
                asset_access_revalidation_required: true,
              },
            }
        : {}),
    };
    operations.push({
      operation_id: `${operationPrefix}-${index++}`,
      type: "CREATE_NODE",
      target_ids: [nextId],
      expected_document_version: version,
      payload: { node, parent_id: nextParentId },
      reason: "canvas-paste",
    });
  }
  return operations;
}
