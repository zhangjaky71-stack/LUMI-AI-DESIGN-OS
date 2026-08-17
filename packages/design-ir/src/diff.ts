import { canonicalStringify } from "./canonical";
import type { DesignDocument, DesignNode, SemanticDiff } from "./types";

const GEOMETRY_KEYS = new Set(["transform", "bounds", "x", "y", "width", "height", "rotation_deg"]);
const TEXT_KEYS = new Set(["content", "spans"]);
const ASSET_KEYS = new Set(["asset_id", "source_artifact_version_id"]);
const CONSTRAINT_KEYS = new Set(["constraint_refs"]);

function changedKeys(before: DesignNode, after: DesignNode): readonly string[] {
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  return [...keys].filter(
    (key) =>
      canonicalStringify(before[key] ?? null) !== canonicalStringify(after[key] ?? null),
  );
}

export function computeSemanticDiff(
  before: DesignDocument,
  after: DesignDocument,
): SemanticDiff {
  const beforeIds = new Set(Object.keys(before.nodes));
  const afterIds = new Set(Object.keys(after.nodes));
  const common = [...beforeIds].filter((id) => afterIds.has(id));
  const properties = new Set<string>();
  const text = new Set<string>();
  const geometry = new Set<string>();
  const assets = new Set<string>();
  const constraints = new Set<string>();

  for (const id of common) {
    const left = before.nodes[id]!;
    const right = after.nodes[id]!;
    for (const key of changedKeys(left, right)) {
      if (TEXT_KEYS.has(key)) text.add(id);
      else if (GEOMETRY_KEYS.has(key)) geometry.add(id);
      else if (ASSET_KEYS.has(key)) assets.add(id);
      else if (CONSTRAINT_KEYS.has(key)) constraints.add(id);
      else properties.add(`${id}:${key}`);
    }
  }
  return {
    nodes_added: [...afterIds].filter((id) => !beforeIds.has(id)).sort(),
    nodes_removed: [...beforeIds].filter((id) => !afterIds.has(id)).sort(),
    properties_changed: [...properties].sort(),
    text_changed: [...text].sort(),
    geometry_changed: [...geometry].sort(),
    asset_replaced: [...assets].sort(),
    constraints_changed: [...constraints].sort(),
  };
}
