import type {
  DesignDocumentLike,
  DesignOperationLike,
  RuntimeConstraint,
  ValidationPolicy,
} from "./types";

export function impactSet(
  document: DesignDocumentLike,
  operation: DesignOperationLike | undefined,
  constraints: readonly RuntimeConstraint[],
  policy: ValidationPolicy,
  forceFull = false,
): { readonly nodeIds: ReadonlySet<string>; readonly fallbackFullScan: boolean } {
  const all = new Set(Object.keys(document.nodes));
  if (forceFull || !operation) return { nodeIds: all, fallbackFullScan: true };
  const values = new Set(operation.target_ids);
  for (const id of [...values]) {
    const node = document.nodes[id];
    if (!node) continue;
    if (node.parent_id) values.add(node.parent_id);
    for (const child of node.children) values.add(child);
  }
  for (const constraint of constraints) {
    const scoped = constraint.scope?.node_ids ?? [];
    if (scoped.some((id) => values.has(id))) for (const id of scoped) values.add(id);
  }
  const ratio = policy.incremental_full_scan_ratio ?? 0.4;
  const limit = policy.incremental_full_scan_node_limit ?? 500;
  const threshold = Math.min(limit, Math.max(1, Math.floor(all.size * ratio)));
  return values.size >= threshold
    ? { nodeIds: all, fallbackFullScan: true }
    : { nodeIds: values, fallbackFullScan: false };
}
