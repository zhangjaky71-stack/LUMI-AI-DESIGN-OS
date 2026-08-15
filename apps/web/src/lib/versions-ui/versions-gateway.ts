import {
  ArtifactEngine,
  type Artifact,
  type ArtifactBranch,
  type ArtifactVersion,
} from "@lumi/artifact-sdk";
import { LumiApiClient } from "@/lib/app-shell/api-client";
import {
  exactCompareChanges,
  renderSemanticSummary,
  safeProvenance,
  validateForkInput,
  validateRestoreInput,
  versionsProblem,
} from "./contracts";
import type {
  ArtifactVersionOption,
  ForkVersionInput,
  RestoreVersionInput,
  SafeVersionProvenance,
  VersionApprovalSummary,
  VersionCompareResult,
  VersionPreview,
  VersionQualitySummary,
  VersionSemanticChange,
  VersionTimelineItem,
  VersionsBootstrap,
  VersionsBootstrapSeed,
  VersionWorkspaceSnapshot,
} from "./types";

export interface VersionsGateway {
  getWorkspace(
    organizationId: string,
    projectId: string,
    artifactId?: string | null,
    signal?: AbortSignal,
  ): Promise<VersionWorkspaceSnapshot>;
  compare(
    organizationId: string,
    artifactId: string,
    fromVersionId: string,
    toVersionId: string,
    signal?: AbortSignal,
  ): Promise<VersionCompareResult>;
  restore(
    organizationId: string,
    projectId: string,
    input: RestoreVersionInput,
    signal?: AbortSignal,
  ): Promise<VersionWorkspaceSnapshot>;
  fork(
    organizationId: string,
    projectId: string,
    input: ForkVersionInput,
    signal?: AbortSignal,
  ): Promise<VersionWorkspaceSnapshot>;
  getProvenance(
    organizationId: string,
    artifactVersionId: string,
    signal?: AbortSignal,
  ): Promise<SafeVersionProvenance>;
  checkForUpdates(
    organizationId: string,
    projectId: string,
    artifactId: string,
    signal?: AbortSignal,
  ): Promise<VersionWorkspaceSnapshot>;
}

function request(signal?: AbortSignal): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

export class HttpVersionsGateway implements VersionsGateway {
  readonly #api: LumiApiClient;

  constructor(api: LumiApiClient) {
    this.#api = api;
  }

  getWorkspace(
    _organizationId: string,
    projectId: string,
    artifactId?: string | null,
    signal?: AbortSignal,
  ) {
    const query = new URLSearchParams();
    if (artifactId) query.set("artifact_id", artifactId);
    const suffix = query.size ? `?${query.toString()}` : "";
    return this.#api.get<VersionWorkspaceSnapshot>(
      `/projects/${encodeURIComponent(projectId)}/versions${suffix}`,
      request(signal),
    );
  }

  compare(
    _organizationId: string,
    artifactId: string,
    fromVersionId: string,
    toVersionId: string,
    signal?: AbortSignal,
  ) {
    const query = new URLSearchParams({ from: fromVersionId, to: toVersionId });
    return this.#api.get<VersionCompareResult>(
      `/artifacts/${encodeURIComponent(artifactId)}/versions/compare?${query.toString()}`,
      request(signal),
    );
  }

  restore(
    _organizationId: string,
    projectId: string,
    input: RestoreVersionInput,
    signal?: AbortSignal,
  ) {
    const safe = validateRestoreInput(input);
    return this.#api.post<VersionWorkspaceSnapshot, Record<string, unknown>>(
      `/artifact-branches/${encodeURIComponent(safe.branch_id)}/restore`,
      {
        project_id: projectId,
        artifact_id: safe.artifact_id,
        source_version_id: safe.source_version_id,
        expected_head_version_id: safe.expected_head_version_id,
      },
      { idempotency_key: crypto.randomUUID(), ...request(signal) },
    );
  }

  fork(
    _organizationId: string,
    projectId: string,
    input: ForkVersionInput,
    signal?: AbortSignal,
  ) {
    const safe = validateForkInput(input);
    return this.#api.post<VersionWorkspaceSnapshot, Record<string, unknown>>(
      `/artifacts/${encodeURIComponent(safe.artifact_id)}/branches`,
      {
        project_id: projectId,
        source_version_id: safe.source_version_id,
        name: safe.name,
      },
      { idempotency_key: crypto.randomUUID(), ...request(signal) },
    );
  }

  getProvenance(
    _organizationId: string,
    artifactVersionId: string,
    signal?: AbortSignal,
  ) {
    return this.#api.get<SafeVersionProvenance>(
      `/artifact-versions/${encodeURIComponent(artifactVersionId)}/provenance:safe`,
      request(signal),
    );
  }

  checkForUpdates(
    _organizationId: string,
    projectId: string,
    artifactId: string,
    signal?: AbortSignal,
  ) {
    const query = new URLSearchParams({ artifact_id: artifactId, check_updates: "1" });
    return this.#api.get<VersionWorkspaceSnapshot>(
      `/projects/${encodeURIComponent(projectId)}/versions?${query.toString()}`,
      request(signal),
    );
  }
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function formatValue(value: VersionSemanticChange["before"]): string {
  return value === null ? "∅" : String(value);
}

export class DeterministicVersionsGateway implements VersionsGateway {
  readonly #engine = new ArtifactEngine();
  readonly #seed: VersionsBootstrapSeed;
  readonly #semantic = new Map<string, readonly VersionSemanticChange[]>();
  readonly #previews = new Map<string, VersionPreview>();
  readonly #approval = new Map<string, VersionApprovalSummary>();
  readonly #quality = new Map<string, VersionQualitySummary>();
  readonly #summaries = new Map<string, string>();
  readonly #activeBranchByArtifact = new Map<string, string>();
  #revision = 1;
  #counter = 100;
  #concurrentHeadVersionId: string | null = null;
  #updatesInjected = false;
  #notice: VersionWorkspaceSnapshot["notice"] = null;

  constructor(seed: VersionsBootstrapSeed) {
    this.#seed = clone(seed);
    for (const artifact of seed.artifacts) this.#engine.addArtifact(artifact);
    for (const branch of seed.branches) {
      this.#engine.addBranch({ ...branch, head_version_id: null });
      this.#activeBranchByArtifact.set(branch.artifact_id, branch.id);
    }
    for (const item of [...seed.versions].sort((a, b) => a.version_number - b.version_number)) {
      this.#engine.addVersion(item);
    }
    for (const edge of seed.lineage) this.#engine.addEdge(edge);
    for (const row of seed.provenance) this.#engine.addProvenance(row);
    for (const [id, value] of Object.entries(seed.semantic_changes)) this.#semantic.set(id, clone(value));
    for (const [id, value] of Object.entries(seed.previews)) this.#previews.set(id, clone(value));
    for (const [id, value] of Object.entries(seed.approval)) this.#approval.set(id, clone(value));
    for (const [id, value] of Object.entries(seed.quality)) this.#quality.set(id, clone(value));
    for (const [id, value] of Object.entries(seed.safe_summaries)) this.#summaries.set(id, value);
  }

  async getWorkspace(
    organizationId: string,
    projectId: string,
    artifactId?: string | null,
    signal?: AbortSignal,
  ) {
    this.#assertScope(organizationId, projectId, signal);
    return this.#snapshot(artifactId ?? this.#seed.active_artifact_id);
  }

  async compare(
    organizationId: string,
    artifactId: string,
    fromVersionId: string,
    toVersionId: string,
    signal?: AbortSignal,
  ) {
    this.#assertOrganization(organizationId, signal);
    const artifact = this.#artifact(artifactId);
    const from = this.#timelineItem(fromVersionId);
    const to = this.#timelineItem(toVersionId);
    if (from.version.artifact_id !== artifact.id || to.version.artifact_id !== artifact.id) {
      throw versionsProblem("COMPARE_ARTIFACT_MISMATCH", 400);
    }
    return clone({
      artifact_id: artifact.id,
      from_version_id: from.version.id,
      to_version_id: to.version.id,
      kind:
        from.preview.kind === "RASTER" || to.preview.kind === "RASTER"
          ? ("RASTER" as const)
          : ("DESIGN_IR" as const),
      before: from,
      after: to,
      semantic_changes: this.#exactSemanticCompare(from, to),
      exact: true as const,
    });
  }

  async restore(
    organizationId: string,
    projectId: string,
    input: RestoreVersionInput,
    signal?: AbortSignal,
  ) {
    this.#assertScope(organizationId, projectId, signal);
    const safe = validateRestoreInput(input);
    const artifact = this.#artifact(safe.artifact_id);
    const source = this.#version(safe.source_version_id);
    const branch = this.#engine.branches.get(safe.branch_id);
    if (!branch || branch.artifact_id !== artifact.id || source.artifact_id !== artifact.id) {
      throw versionsProblem("RESTORE_SCOPE_MISMATCH", 400);
    }
    if (branch.head_version_id !== safe.expected_head_version_id) {
      throw versionsProblem("BRANCH_HEAD_CONFLICT", 409);
    }

    const restored = this.#engine.restore(
      source.id,
      branch.id,
      {
        id: `${artifact.id}-restore-${++this.#counter}`,
        version_number: this.#engine.nextVersionNumber(artifact.id),
        constraint_snapshot_hash: source.constraint_snapshot_hash,
        created_by_type: "USER",
        created_by_id: "user:owner",
        created_at: "2026-08-15T05:10:00.000Z",
        ...(source.brand_rule_set_version
          ? { brand_rule_set_version: source.brand_rule_set_version }
          : {}),
        ...(source.identity_validation_snapshot_id
          ? { identity_validation_snapshot_id: source.identity_validation_snapshot_id }
          : {}),
      },
      `edge-restore-${this.#counter}`,
    );

    this.#semantic.set(restored.id, [
      {
        id: `semantic-restore-${this.#counter}`,
        kind: "OTHER",
        label: `Restored content from v${source.version_number}; later history preserved`,
        node_id: null,
        node_name: null,
        property: "restore_source_version_id",
        before: restored.parent_version_id,
        after: source.id,
        protected_identity: false,
      },
    ]);
    this.#previews.set(restored.id, clone(this.#preview(source.id)));
    this.#approval.set(restored.id, {
      status: "DRAFT",
      approved_by: null,
      approved_at: null,
      validation_label: null,
    });
    this.#quality.set(restored.id, {
      score: null,
      label: "Not scored",
      checks: ["Restore lineage recorded"],
    });
    this.#summaries.set(
      restored.id,
      `Restored immutable content from v${source.version_number} into a new DRAFT version.`,
    );

    const sourceProvenance = this.#engine.provenance.get(source.id);
    this.#engine.addProvenance({
      artifact_version_id: restored.id,
      organization_id: restored.organization_id,
      constraint_snapshot_hash: restored.constraint_snapshot_hash,
      code_git_sha: sourceProvenance?.code_git_sha ?? "unknown",
      ...(sourceProvenance?.compiler ? { compiler: clone(sourceProvenance.compiler) } : {}),
      ...(restored.brand_rule_set_version
        ? { brand_rule_set_version: restored.brand_rule_set_version }
        : {}),
      ...(restored.identity_validation_snapshot_id
        ? { identity_validation_snapshot_id: restored.identity_validation_snapshot_id }
        : {}),
      input_artifact_version_ids: [source.id],
      prompt_template_version: "restore@1",
      skill_versions: {},
    });

    this.#revision += 1;
    this.#activeBranchByArtifact.set(artifact.id, branch.id);
    this.#notice = {
      kind: "INFO",
      message: `v${source.version_number} was restored as new DRAFT v${restored.version_number}; no history was deleted.`,
    };
    return this.#snapshot(artifact.id);
  }

  async fork(
    organizationId: string,
    projectId: string,
    input: ForkVersionInput,
    signal?: AbortSignal,
  ) {
    this.#assertScope(organizationId, projectId, signal);
    const safe = validateForkInput(input);
    const artifact = this.#artifact(safe.artifact_id);
    const source = this.#version(safe.source_version_id);
    if (source.artifact_id !== artifact.id) throw versionsProblem("FORK_SCOPE_MISMATCH", 400);

    const branch: ArtifactBranch = {
      id: `branch-${artifact.id}-${++this.#counter}`,
      organization_id: artifact.organization_id,
      artifact_id: artifact.id,
      name: safe.name,
      base_version_id: source.id,
      head_version_id: source.id,
      created_by: "user:owner",
    };
    try {
      this.#engine.addBranch(branch);
    } catch {
      throw versionsProblem("BRANCH_NAME_CONFLICT", 409);
    }
    this.#activeBranchByArtifact.set(artifact.id, branch.id);
    this.#revision += 1;
    this.#notice = {
      kind: "INFO",
      message: `Branch ${branch.name} created from exact v${source.version_number}.`,
    };
    return this.#snapshot(artifact.id);
  }

  async getProvenance(
    organizationId: string,
    artifactVersionId: string,
    signal?: AbortSignal,
  ): Promise<SafeVersionProvenance> {
    this.#assertOrganization(organizationId, signal);
    if (!this.#seed.provenance_access) throw versionsProblem("PROVENANCE_FORBIDDEN", 403);
    const item = this.#timelineItem(artifactVersionId);
    const source = this.#engine.provenance.get(artifactVersionId);
    if (!source) throw versionsProblem("PROVENANCE_NOT_FOUND", 404);
    return clone(
      safeProvenance(item, {
        ...(source.model ? { model: source.model } : {}),
        ...(source.provider ? { provider: source.provider } : {}),
        ...(source.agent_run_id ? { agent_run_id: source.agent_run_id } : {}),
        ...(source.task_id ? { task_id: source.task_id } : {}),
        ...(source.generation_id ? { generation_id: source.generation_id } : {}),
        ...(source.recipe_version ? { recipe_version: source.recipe_version } : {}),
        ...(source.skill_versions ? { skill_versions: source.skill_versions } : {}),
        ...(source.input_asset_ids ? { input_asset_ids: source.input_asset_ids } : {}),
        ...(source.input_artifact_version_ids
          ? { input_artifact_version_ids: source.input_artifact_version_ids }
          : {}),
        ...(source.brand_rule_set_version
          ? { brand_rule_set_version: source.brand_rule_set_version }
          : {}),
        constraint_snapshot_hash: source.constraint_snapshot_hash,
        ...(source.prompt_hash ? { prompt_hash: source.prompt_hash } : {}),
        ...(source.prompt_template_version
          ? { prompt_template_version: source.prompt_template_version }
          : {}),
        code_git_sha: source.code_git_sha,
        ...(source.compiler ? { compiler: source.compiler } : {}),
      }),
    );
  }

  async checkForUpdates(
    organizationId: string,
    projectId: string,
    artifactId: string,
    signal?: AbortSignal,
  ) {
    this.#assertScope(organizationId, projectId, signal);
    const artifact = this.#artifact(artifactId);
    if (!this.#updatesInjected) this.#injectConcurrentHead(artifact);
    return this.#snapshot(artifact.id);
  }

  #snapshot(artifactId: string): VersionWorkspaceSnapshot {
    const artifact = this.#artifact(artifactId);
    const branches = [...this.#engine.branches.values()].filter(
      (branch) => branch.artifact_id === artifact.id,
    );
    const activeBranchId = this.#activeBranchByArtifact.get(artifact.id) ?? branches[0]?.id;
    if (!activeBranchId) throw versionsProblem("ARTIFACT_BRANCH_MISSING", 500);
    const activeBranch = this.#engine.branches.get(activeBranchId);
    if (!activeBranch) throw versionsProblem("ARTIFACT_BRANCH_MISSING", 500);

    const versions = [...this.#engine.versions.values()]
      .filter((item) => item.artifact_id === artifact.id)
      .sort((a, b) => b.version_number - a.version_number)
      .map((item) => this.#timelineItem(item.id));
    const lineage = [...this.#engine.edges.values()].filter((edge) => {
      const from = this.#engine.versions.get(edge.from_version_id);
      return from?.artifact_id === artifact.id;
    });
    const artifactOptions: ArtifactVersionOption[] = [...this.#engine.artifacts.values()].map(
      (candidate) => {
        const candidateBranches = [...this.#engine.branches.values()].filter(
          (branch) => branch.artifact_id === candidate.id,
        );
        const candidateVersions = [...this.#engine.versions.values()].filter(
          (item) => item.artifact_id === candidate.id,
        );
        const main = candidateBranches.find((branch) => branch.name === "main") ?? candidateBranches[0];
        return {
          artifact_id: candidate.id,
          title: candidate.title,
          type: candidate.type,
          branch_count: candidateBranches.length,
          version_count: candidateVersions.length,
          head_version_id: main?.head_version_id ?? null,
        };
      },
    );

    return clone({
      project_id: this.#seed.project_id,
      project_name: this.#seed.project_name,
      revision: this.#revision,
      artifact_options: artifactOptions,
      active_artifact: artifact,
      branches,
      versions,
      lineage,
      active_branch_id: activeBranch.id,
      head_version_id: activeBranch.head_version_id,
      can_view_provenance: this.#seed.provenance_access,
      concurrent_head_version_id: this.#concurrentHeadVersionId,
      notice: this.#notice,
    });
  }

  #timelineItem(versionId: string): VersionTimelineItem {
    const version = this.#version(versionId);
    const branch = this.#engine.branches.get(version.branch_id);
    if (!branch) throw versionsProblem("VERSION_BRANCH_MISSING", 500);
    const semantic = this.#semantic.get(version.id) ?? [];
    const approval = this.#approval.get(version.id) ?? {
      status: version.status,
      approved_by: null,
      approved_at: null,
      validation_label: null,
    };
    const quality = this.#quality.get(version.id) ?? {
      score: version.quality_score ?? null,
      label: version.quality_score == null ? "Not scored" : "Ready",
      checks: [],
    };
    const lineageLabels = [...this.#engine.edges.values()]
      .filter((edge) => edge.to_version_id === version.id)
      .map((edge) => `${edge.type} · ${edge.from_version_id}`);
    return {
      version: clone(version),
      branch_name: branch.name,
      semantic_changes: clone(semantic),
      preview: clone(this.#preview(version.id)),
      approval: clone(approval),
      quality: clone(quality),
      safe_change_summary: this.#summaries.get(version.id) ?? renderSemanticSummary(semantic),
      lineage_labels: lineageLabels,
    };
  }

  #exactSemanticCompare(
    from: VersionTimelineItem,
    to: VersionTimelineItem,
  ): readonly VersionSemanticChange[] {
    if (from.version.id === to.version.id) return [];
    if (to.version.parent_version_id === from.version.id) {
      return clone(exactCompareChanges(from, to));
    }

    const low = Math.min(from.version.version_number, to.version.version_number);
    const high = Math.max(from.version.version_number, to.version.version_number);
    const forward = from.version.version_number < to.version.version_number;
    const rows = [...this.#engine.versions.values()]
      .filter((item) => item.artifact_id === from.version.artifact_id)
      .filter((item) => item.version_number > low && item.version_number <= high)
      .sort((a, b) => a.version_number - b.version_number)
      .flatMap((item) => this.#semantic.get(item.id) ?? []);
    const merged = new Map<string, VersionSemanticChange>();
    for (const row of rows) {
      const key = `${row.node_id ?? "artifact"}:${row.property}`;
      const current = merged.get(key);
      merged.set(key, current ? { ...row, before: current.before } : { ...row });
    }
    return clone(
      [...merged.values()].map((row) => {
        const before = forward ? row.before : row.after;
        const after = forward ? row.after : row.before;
        return {
          ...row,
          before,
          after,
          label: `${row.node_name ?? "Artifact"} · ${row.property}: ${formatValue(before)}→${formatValue(after)}`,
        };
      }),
    );
  }

  #injectConcurrentHead(artifact: Artifact): void {
    const branch = [...this.#engine.branches.values()].find(
      (item) => item.artifact_id === artifact.id && item.name === "main",
    );
    if (!branch) throw versionsProblem("MAIN_BRANCH_MISSING", 500);
    const currentHead = branch.head_version_id ? this.#version(branch.head_version_id) : null;
    if (!currentHead) throw versionsProblem("HEAD_VERSION_MISSING", 500);

    const next: ArtifactVersion = {
      id: `${artifact.id}-external-${++this.#counter}`,
      organization_id: artifact.organization_id,
      artifact_id: artifact.id,
      branch_id: branch.id,
      parent_version_id: currentHead.id,
      schema_version: currentHead.schema_version,
      version_number: this.#engine.nextVersionNumber(artifact.id),
      status: "DRAFT",
      content_hash: "9".repeat(64),
      constraint_snapshot_hash: currentHead.constraint_snapshot_hash,
      created_by_type: "USER",
      created_by_id: "user:collaborator",
      created_at: "2026-08-15T05:20:00.000Z",
      primary_file_id: currentHead.primary_file_id ?? null,
      design_document_version_id: currentHead.design_document_version_id ?? null,
      brand_rule_set_version: currentHead.brand_rule_set_version ?? null,
      identity_validation_snapshot_id: currentHead.identity_validation_snapshot_id ?? null,
      quality_score: null,
    };
    this.#engine.addVersion(next, currentHead.id);
    this.#semantic.set(next.id, [
      {
        id: `semantic-external-${this.#counter}`,
        kind: "LAYOUT",
        label: "Collaborator adjusted footer spacing",
        node_id: "node-footer",
        node_name: "Footer",
        property: "y",
        before: 1220,
        after: 1236,
        protected_identity: false,
      },
    ]);
    this.#previews.set(next.id, clone(this.#preview(currentHead.id)));
    this.#approval.set(next.id, {
      status: "DRAFT",
      approved_by: null,
      approved_at: null,
      validation_label: null,
    });
    this.#quality.set(next.id, {
      score: null,
      label: "Not scored",
      checks: ["Pending validation"],
    });
    this.#summaries.set(next.id, "A collaborator created a newer branch-head version.");
    this.#engine.addProvenance({
      artifact_version_id: next.id,
      organization_id: next.organization_id,
      constraint_snapshot_hash: next.constraint_snapshot_hash,
      code_git_sha: "collaborator-client",
      ...(next.brand_rule_set_version
        ? { brand_rule_set_version: next.brand_rule_set_version }
        : {}),
      input_artifact_version_ids: [currentHead.id],
      prompt_template_version: "manual-edit@1",
      skill_versions: {},
    });
    this.#updatesInjected = true;
    this.#revision += 1;
    this.#concurrentHeadVersionId = next.id;
    this.#notice = {
      kind: "WARNING",
      message: `A newer v${next.version_number} exists. Your current compare targets were not changed.`,
    };
  }

  #preview(versionId: string): VersionPreview {
    const preview = this.#previews.get(versionId);
    if (!preview) throw versionsProblem("VERSION_PREVIEW_MISSING", 500);
    return preview;
  }

  #version(versionId: string): ArtifactVersion {
    const item = this.#engine.versions.get(versionId);
    if (!item) throw versionsProblem("ARTIFACT_VERSION_NOT_FOUND", 404);
    return item;
  }

  #artifact(artifactId: string): Artifact {
    const item = this.#engine.artifacts.get(artifactId);
    if (!item) throw versionsProblem("ARTIFACT_NOT_FOUND", 404);
    return item;
  }

  #assertOrganization(organizationId: string, signal?: AbortSignal): void {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (organizationId !== "org-lumi") throw versionsProblem("ORGANIZATION_FORBIDDEN", 403);
  }

  #assertScope(organizationId: string, projectId: string, signal?: AbortSignal): void {
    this.#assertOrganization(organizationId, signal);
    if (projectId !== this.#seed.project_id) throw versionsProblem("PROJECT_NOT_FOUND", 404);
  }
}

export function getVersionsGateway(api: LumiApiClient, bootstrap: VersionsBootstrap): VersionsGateway {
  if (bootstrap.mode !== "e2e") return new HttpVersionsGateway(api);
  if (!bootstrap.seed) throw new Error("VERSIONS_E2E_SEED_REQUIRED");
  return new DeterministicVersionsGateway(bootstrap.seed);
}
