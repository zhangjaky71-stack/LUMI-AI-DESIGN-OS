import type { DesignDocument, DesignNode } from "../../design-ir/src/index";
import type { CanvasFragment, ClipboardAssetPolicy } from "./types";

function collect(document: DesignDocument, ids: readonly string[]): Set<string> {
  const result = new Set<string>(); const walk = (id: string): void => { if (result.has(id)) return; const node = document.nodes[id]; if (!node) return; result.add(id); node.children.forEach(walk); };
  ids.forEach(walk); return result;
}
export function createFragment(document: DesignDocument, selectedIds: readonly string[], sourceProjectId: string): CanvasFragment {
  const ids = collect(document, selectedIds); const nodes: Record<string, DesignNode> = {};
  for (const id of [...ids].sort()) { const node = document.nodes[id]; if (node) nodes[id] = structuredClone(node); }
  return { schemaVersion: "lumi.canvas-fragment/1.0", sourceProjectId, rootNodeIds: [...selectedIds].filter((id) => ids.has(id)), nodes };
}
export function parseFragment(value: string): CanvasFragment {
  const raw = JSON.parse(value) as Partial<CanvasFragment>;
  if (raw.schemaVersion !== "lumi.canvas-fragment/1.0" || typeof raw.sourceProjectId !== "string" || !Array.isArray(raw.rootNodeIds) || !raw.nodes || typeof raw.nodes !== "object") throw new Error("CANVAS_CLIPBOARD_INVALID");
  return raw as CanvasFragment;
}
export async function remapFragmentAssets(fragment: CanvasFragment, targetProjectId: string, policy: ClipboardAssetPolicy): Promise<CanvasFragment> {
  if (fragment.sourceProjectId === targetProjectId) return fragment;
  const nodes: Record<string, DesignNode> = {};
  for (const [id, node] of Object.entries(fragment.nodes)) {
    const assetId = typeof node.asset_id === "string" ? node.asset_id : null;
    if (!assetId) { nodes[id] = node; continue; }
    const mapped = await policy.remapAsset(assetId, fragment.sourceProjectId, targetProjectId);
    nodes[id] = mapped ? { ...node, asset_id: mapped } : { ...node, asset_id: undefined, metadata: { ...(node.metadata ?? {}), canvas_asset_unavailable: true } };
  }
  return { ...fragment, sourceProjectId: targetProjectId, nodes };
}
