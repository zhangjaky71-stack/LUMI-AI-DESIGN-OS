import type { ArtifactBranch, ArtifactFile, ArtifactVersion } from "./types";

export interface ArtifactGcObject {
  readonly storage_key: string;
  readonly marked_at_ms?: number;
  readonly retention_until_ms?: number;
  readonly legal_hold?: boolean;
}

export function liveArtifactStorageKeys(
  versions: readonly ArtifactVersion[],
  branches: readonly ArtifactBranch[],
  files: readonly ArtifactFile[],
): ReadonlySet<string> {
  const protectedVersions = new Set<string>();
  for (const version of versions) {
    if (["APPROVED", "READY"].includes(version.status)) protectedVersions.add(version.id);
  }
  for (const branch of branches) {
    if (branch.head_version_id) protectedVersions.add(branch.head_version_id);
    if (branch.base_version_id) protectedVersions.add(branch.base_version_id);
  }
  const live = new Set<string>();
  for (const file of files) {
    if (protectedVersions.has(file.artifact_version_id)) live.add(file.storage_key);
  }
  return live;
}

export function markArtifactGcObjects(
  objects: readonly ArtifactGcObject[],
  liveKeys: ReadonlySet<string>,
  nowMs: number,
): readonly ArtifactGcObject[] {
  return objects.map((object) => {
    if (liveKeys.has(object.storage_key) || object.legal_hold || (object.retention_until_ms ?? 0) > nowMs) {
      const { marked_at_ms: _marked, ...rest } = object;
      return rest;
    }
    return object.marked_at_ms === undefined ? { ...object, marked_at_ms: nowMs } : object;
  });
}

export function artifactGcSweepCandidates(
  objects: readonly ArtifactGcObject[],
  liveKeys: ReadonlySet<string>,
  nowMs: number,
  minimumDelayMs: number,
): readonly ArtifactGcObject[] {
  return objects
    .filter((object) =>
      !liveKeys.has(object.storage_key) &&
      !object.legal_hold &&
      object.marked_at_ms !== undefined &&
      nowMs - object.marked_at_ms >= minimumDelayMs &&
      (object.retention_until_ms === undefined || nowMs >= object.retention_until_ms),
    )
    .sort((a, b) => a.storage_key.localeCompare(b.storage_key));
}
