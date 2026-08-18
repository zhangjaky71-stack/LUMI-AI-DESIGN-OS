import type { VersionHistory } from "@/lib/versions/types";

export type BranchHeadSnapshot = ReadonlyMap<string, string | null>;

export function branchHeadSnapshot(history: VersionHistory): Map<string, string | null> {
  return new Map(history.branches.map((branch) => [branch.id, branch.headVersionId]));
}

export function detectNewHead(
  history: VersionHistory,
  baseline: BranchHeadSnapshot,
  viewedVersionId: string,
): string | null {
  const viewed = history.versions.find((item) => item.id === viewedVersionId);
  if (!viewed) return null;
  const oldHead = baseline.get(viewed.branchId) ?? null;
  const currentHead = history.branches.find((branch) => branch.id === viewed.branchId)?.headVersionId ?? null;
  if (!currentHead || currentHead === oldHead || currentHead === viewedVersionId) return null;
  return currentHead;
}
