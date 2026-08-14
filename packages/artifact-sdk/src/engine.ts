import type {
  Artifact,
  ArtifactBranch,
  ArtifactFile,
  ArtifactLineageEdge,
  ArtifactObjectStore,
  ArtifactProvenance,
  ArtifactVersion,
  ArtifactVersionStatus,
} from "./types";

const SHA256 = /^[0-9a-f]{64}$/;
const TRANSITIONS: Readonly<Record<ArtifactVersionStatus, ReadonlySet<ArtifactVersionStatus>>> = {
  DRAFT: new Set(["READY", "REJECTED", "ARCHIVED"]),
  READY: new Set(["APPROVED", "REJECTED", "ARCHIVED"]),
  APPROVED: new Set(["ARCHIVED"]),
  REJECTED: new Set(["ARCHIVED"]),
  ARCHIVED: new Set(),
};

export class ArtifactEngineError extends Error {}
export class ArtifactBranchConflictError extends ArtifactEngineError {}
export class ArtifactImmutableError extends ArtifactEngineError {}

function assertTenant(expected: string, actual: string): void {
  if (expected !== actual) throw new ArtifactEngineError("organization scope mismatch");
}

export class ArtifactEngine {
  readonly artifacts = new Map<string, Artifact>();
  readonly branches = new Map<string, ArtifactBranch>();
  readonly versions = new Map<string, ArtifactVersion>();
  readonly files = new Map<string, ArtifactFile>();
  readonly edges = new Map<string, ArtifactLineageEdge>();
  readonly provenance = new Map<string, ArtifactProvenance>();

  addArtifact(value: Artifact): void {
    if (this.artifacts.has(value.id)) throw new ArtifactEngineError("artifact already exists");
    this.artifacts.set(value.id, structuredClone(value));
  }

  addBranch(value: ArtifactBranch): void {
    const artifact = this.artifacts.get(value.artifact_id);
    if (!artifact) throw new ArtifactEngineError("branch artifact missing");
    assertTenant(artifact.organization_id, value.organization_id);
    if ([...this.branches.values()].some((b) => b.artifact_id === value.artifact_id && b.name === value.name)) {
      throw new ArtifactEngineError("branch name already exists for artifact");
    }
    this.branches.set(value.id, structuredClone(value));
  }

  nextVersionNumber(artifactId: string): number {
    return Math.max(0, ...[...this.versions.values()].filter((v) => v.artifact_id === artifactId).map((v) => v.version_number)) + 1;
  }

  addVersion(value: ArtifactVersion, expectedBranchHead?: string | null): void {
    if (!SHA256.test(value.content_hash) || !SHA256.test(value.constraint_snapshot_hash)) {
      throw new ArtifactEngineError("version hashes must be lowercase SHA-256");
    }
    const artifact = this.artifacts.get(value.artifact_id);
    const branch = this.branches.get(value.branch_id);
    if (!artifact || !branch || branch.artifact_id !== value.artifact_id) throw new ArtifactEngineError("version artifact/branch missing");
    assertTenant(artifact.organization_id, value.organization_id);
    assertTenant(branch.organization_id, value.organization_id);
    if (expectedBranchHead !== undefined && branch.head_version_id !== expectedBranchHead) {
      throw new ArtifactBranchConflictError("branch head compare-and-swap conflict");
    }
    if ([...this.versions.values()].some((v) => v.artifact_id === value.artifact_id && v.version_number === value.version_number)) {
      throw new ArtifactEngineError("artifact version number already used");
    }
    if (value.parent_version_id) {
      const parent = this.versions.get(value.parent_version_id);
      if (!parent || parent.artifact_id !== value.artifact_id || parent.organization_id !== value.organization_id) {
        throw new ArtifactEngineError("invalid parent version");
      }
    }
    this.versions.set(value.id, structuredClone(value));
    this.branches.set(branch.id, { ...branch, head_version_id: value.id });
  }

  updateBranchHead(branchId: string, expectedHead: string | null, nextHead: string): ArtifactBranch {
    const branch = this.branches.get(branchId);
    const version = this.versions.get(nextHead);
    if (!branch || !version || version.artifact_id !== branch.artifact_id || version.organization_id !== branch.organization_id) {
      throw new ArtifactEngineError("invalid branch head");
    }
    if (branch.head_version_id !== expectedHead) throw new ArtifactBranchConflictError("branch head compare-and-swap conflict");
    const updated = { ...branch, head_version_id: nextHead };
    this.branches.set(branchId, updated);
    return updated;
  }

  transition(versionId: string, target: ArtifactVersionStatus, validationPassed = false, qualityScore?: number): ArtifactVersion {
    const version = this.versions.get(versionId);
    if (!version) throw new ArtifactEngineError("version missing");
    if (!TRANSITIONS[version.status].has(target)) throw new ArtifactEngineError(`invalid transition ${version.status}->${target}`);
    if (target === "APPROVED" && !validationPassed) throw new ArtifactEngineError("APPROVED requires validation");
    const updated = { ...version, status: target, ...(qualityScore !== undefined ? { quality_score: qualityScore } : {}) };
    this.versions.set(versionId, updated);
    return updated;
  }

  addProvenance(value: ArtifactProvenance): void {
    const version = this.versions.get(value.artifact_version_id);
    if (!version) throw new ArtifactEngineError("provenance version missing");
    assertTenant(version.organization_id, value.organization_id);
    if (version.constraint_snapshot_hash !== value.constraint_snapshot_hash) throw new ArtifactEngineError("constraint snapshot mismatch");
    if (this.provenance.has(value.artifact_version_id)) throw new ArtifactImmutableError("provenance is immutable");
    this.provenance.set(value.artifact_version_id, structuredClone(value));
  }

  async attachVerifiedFile(value: ArtifactFile, store: ArtifactObjectStore): Promise<void> {
    const version = this.versions.get(value.artifact_version_id);
    if (!version) throw new ArtifactEngineError("file version missing");
    assertTenant(version.organization_id, value.organization_id);
    if (value.storage_key.includes("://")) throw new ArtifactEngineError("storage_key must not be a URL");
    if ([...this.files.values()].some((f) => f.artifact_version_id === value.artifact_version_id && f.role === value.role)) {
      throw new ArtifactEngineError("file role already attached");
    }
    const stat = await store.stat(value.storage_key);
    if (!stat) throw new ArtifactEngineError("storage object missing");
    if (stat.checksum_sha256 !== value.checksum_sha256) throw new ArtifactEngineError("storage checksum mismatch");
    if (stat.size_bytes !== value.size_bytes) throw new ArtifactEngineError("storage size mismatch");
    if (stat.mime_type && stat.mime_type !== value.mime_type) throw new ArtifactEngineError("storage MIME mismatch");
    this.files.set(value.id, structuredClone(value));
  }

  addEdge(value: ArtifactLineageEdge): void {
    if (value.from_version_id === value.to_version_id) throw new ArtifactEngineError("lineage self-loop forbidden");
    const source = this.versions.get(value.from_version_id);
    const target = this.versions.get(value.to_version_id);
    if (!source || !target) throw new ArtifactEngineError("lineage endpoints missing");
    assertTenant(source.organization_id, target.organization_id);
    assertTenant(source.organization_id, value.organization_id);
    if (this.reachable(value.to_version_id, value.from_version_id)) throw new ArtifactEngineError("lineage cycle forbidden");
    this.edges.set(value.id, structuredClone(value));
  }

  restore(sourceVersionId: string, branchId: string, input: Omit<ArtifactVersion, "artifact_id" | "organization_id" | "branch_id" | "parent_version_id" | "schema_version" | "content_hash" | "primary_file_id" | "design_document_version_id" | "quality_score" | "status">, edgeId: string): ArtifactVersion {
    const source = this.versions.get(sourceVersionId);
    const branch = this.branches.get(branchId);
    if (!source || !branch || branch.artifact_id !== source.artifact_id) throw new ArtifactEngineError("restore source/branch invalid");
    const restored: ArtifactVersion = {
      ...input,
      organization_id: source.organization_id,
      artifact_id: source.artifact_id,
      branch_id: branch.id,
      parent_version_id: branch.head_version_id,
      schema_version: source.schema_version,
      status: "DRAFT",
      content_hash: source.content_hash,
      primary_file_id: source.primary_file_id ?? null,
      design_document_version_id: source.design_document_version_id ?? null,
      quality_score: null,
    };
    this.addVersion(restored, branch.head_version_id);
    this.addEdge({ id: edgeId, organization_id: source.organization_id, from_version_id: source.id, to_version_id: restored.id, type: "DERIVED_FROM", metadata: { operation: "RESTORE" } });
    return restored;
  }

  private reachable(start: string, goal: string): boolean {
    const pending = [start];
    const seen = new Set<string>();
    while (pending.length) {
      const current = pending.pop()!;
      if (current === goal) return true;
      if (seen.has(current)) continue;
      seen.add(current);
      for (const edge of this.edges.values()) if (edge.from_version_id === current) pending.push(edge.to_version_id);
    }
    return false;
  }
}
