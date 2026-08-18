export type ArtifactVersionStatus = "DRAFT" | "READY" | "APPROVED" | "REJECTED" | "ARCHIVED";
export type CreatedByType = "USER" | "AGENT" | "SYSTEM" | "IMPORT";

export type VersionArtifact = {
  id: string;
  projectId: string;
  type: string;
  name: string;
  designDocumentId: string | null;
};

export type VersionBranch = {
  id: string;
  artifactId: string;
  name: string;
  baseVersionId: string | null;
  headVersionId: string | null;
  createdByType: CreatedByType;
  createdById: string | null;
  createdAt: string;
};

export type VersionPreview = {
  mimeType: string | null;
  width: number | null;
  height: number | null;
  durationMs: number | null;
};

export type VersionHistoryItem = {
  id: string;
  artifactId: string;
  branchId: string;
  parentVersionId: string | null;
  versionNumber: number;
  status: ArtifactVersionStatus;
  contentHash: string;
  designDocumentVersionId: string | null;
  qualityScore: number | null;
  constraintSnapshotHash: string | null;
  createdByType: CreatedByType;
  createdById: string | null;
  createdAt: string;
  preview: VersionPreview;
};

export type VersionHistory = {
  artifact: VersionArtifact;
  branches: readonly VersionBranch[];
  versions: readonly VersionHistoryItem[];
};

export type SafeSkillVersion = { skillId: string; version: string };
export type SafeVersionProvenance = {
  artifactVersionId: string;
  traceabilityScore: number;
  traceabilityStatus: string;
  missingFields: readonly string[];
  agentRunId: string | null;
  taskId: string | null;
  generationId: string | null;
  provider: string | null;
  model: string | null;
  promptHash: string | null;
  promptTemplateVersion: string | null;
  inputAssetIds: readonly string[];
  inputArtifactVersionIds: readonly string[];
  designIrSchemaVersion: string | null;
  constraintSnapshotHash: string | null;
  recipeVersion: string | null;
  skillVersions: readonly SafeSkillVersion[];
  codeGitSha: string;
  compilerVersion: string | null;
  agentVersion: string | null;
};

export type SemanticDiff = {
  nodesAdded: readonly string[];
  nodesRemoved: readonly string[];
  propertiesChanged: readonly string[];
  textChanged: readonly string[];
  geometryChanged: readonly string[];
  assetReplaced: readonly string[];
  constraintsChanged: readonly string[];
};

export type VersionCompare = {
  leftVersionId: string;
  rightVersionId: string;
  kind: "DESIGN_SEMANTIC" | "RASTER_METADATA" | "GENERIC_METADATA";
  equalContentHash: boolean;
  semanticDiff: SemanticDiff | null;
  visualMetrics: Readonly<Record<string, number>> | null;
};

export type SemanticChange = {
  category: "added" | "removed" | "property" | "text" | "geometry" | "asset" | "constraint";
  subject: string;
  property?: string;
};

export function parseVersionHistory(value: unknown): VersionHistory {
  const record = asRecord(value, "VERSION_HISTORY_INVALID");
  return {
    artifact: parseArtifact(record.artifact),
    branches: asArray(record.branches, "VERSION_BRANCHES_INVALID").map(parseBranch),
    versions: asArray(record.versions, "VERSION_ITEMS_INVALID").map(parseVersionItem),
  };
}

export function parseSafeVersionProvenance(value: unknown): SafeVersionProvenance {
  const record = asRecord(value, "VERSION_PROVENANCE_INVALID");
  return {
    artifactVersionId: requiredString(record.artifact_version_id ?? record.artifactVersionId, "VERSION_PROVENANCE_ID_REQUIRED"),
    traceabilityScore: finiteNumber(record.traceability_score ?? record.traceabilityScore, "VERSION_TRACEABILITY_INVALID", 0, 1),
    traceabilityStatus: requiredString(record.traceability_status ?? record.traceabilityStatus, "VERSION_TRACEABILITY_STATUS_REQUIRED"),
    missingFields: stringArray(record.missing_fields ?? record.missingFields ?? [], "VERSION_MISSING_FIELDS_INVALID"),
    agentRunId: nullableString(record.agent_run_id ?? record.agentRunId),
    taskId: nullableString(record.task_id ?? record.taskId),
    generationId: nullableString(record.generation_id ?? record.generationId),
    provider: nullableString(record.provider),
    model: nullableString(record.model),
    promptHash: nullableSha256(record.prompt_hash ?? record.promptHash),
    promptTemplateVersion: nullableString(record.prompt_template_version ?? record.promptTemplateVersion),
    inputAssetIds: stringArray(record.input_asset_ids ?? record.inputAssetIds ?? [], "VERSION_INPUT_ASSETS_INVALID"),
    inputArtifactVersionIds: stringArray(record.input_artifact_version_ids ?? record.inputArtifactVersionIds ?? [], "VERSION_INPUT_VERSIONS_INVALID"),
    designIrSchemaVersion: nullableString(record.design_ir_schema_version ?? record.designIrSchemaVersion),
    constraintSnapshotHash: nullableSha256(record.constraint_snapshot_hash ?? record.constraintSnapshotHash),
    recipeVersion: nullableString(record.recipe_version ?? record.recipeVersion),
    skillVersions: asArray(record.skill_versions ?? record.skillVersions ?? [], "VERSION_SKILLS_INVALID").map((item) => {
      const skill = asRecord(item, "VERSION_SKILL_INVALID");
      return {
        skillId: requiredString(skill.skill_id ?? skill.skillId, "VERSION_SKILL_ID_REQUIRED"),
        version: requiredString(skill.version, "VERSION_SKILL_VERSION_REQUIRED"),
      };
    }),
    codeGitSha: gitSha(record.code_git_sha ?? record.codeGitSha),
    compilerVersion: nullableString(record.compiler_version ?? record.compilerVersion),
    agentVersion: nullableString(record.agent_version ?? record.agentVersion),
  };
}

export function parseVersionCompare(value: unknown): VersionCompare {
  const record = asRecord(value, "VERSION_COMPARE_INVALID");
  const kind = enumValue(record.kind, ["DESIGN_SEMANTIC", "RASTER_METADATA", "GENERIC_METADATA"] as const, "VERSION_COMPARE_KIND_INVALID");
  return {
    leftVersionId: requiredString(record.left_version_id ?? record.leftVersionId, "VERSION_COMPARE_LEFT_REQUIRED"),
    rightVersionId: requiredString(record.right_version_id ?? record.rightVersionId, "VERSION_COMPARE_RIGHT_REQUIRED"),
    kind,
    equalContentHash: requiredBoolean(record.equal_content_hash ?? record.equalContentHash, "VERSION_COMPARE_HASH_FLAG_REQUIRED"),
    semanticDiff: parseSemanticDiff(record.semantic_diff ?? record.semanticDiff),
    visualMetrics: parseVisualMetrics(record.visual_metrics ?? record.visualMetrics),
  };
}

export function semanticChanges(diff: SemanticDiff | null): readonly SemanticChange[] {
  if (!diff) return [];
  return [
    ...diff.nodesAdded.map((subject) => ({ category: "added" as const, subject })),
    ...diff.nodesRemoved.map((subject) => ({ category: "removed" as const, subject })),
    ...diff.propertiesChanged.map((entry) => {
      const separator = entry.indexOf(":");
      return separator > 0
        ? { category: "property" as const, subject: entry.slice(0, separator), property: entry.slice(separator + 1) }
        : { category: "property" as const, subject: entry };
    }),
    ...diff.textChanged.map((subject) => ({ category: "text" as const, subject })),
    ...diff.geometryChanged.map((subject) => ({ category: "geometry" as const, subject })),
    ...diff.assetReplaced.map((subject) => ({ category: "asset" as const, subject })),
    ...diff.constraintsChanged.map((subject) => ({ category: "constraint" as const, subject })),
  ];
}

function parseArtifact(value: unknown): VersionArtifact {
  const record = asRecord(value, "VERSION_ARTIFACT_INVALID");
  return {
    id: requiredString(record.id, "VERSION_ARTIFACT_ID_REQUIRED"),
    projectId: requiredString(record.project_id ?? record.projectId, "VERSION_PROJECT_ID_REQUIRED"),
    type: requiredString(record.type, "VERSION_ARTIFACT_TYPE_REQUIRED"),
    name: requiredString(record.name, "VERSION_ARTIFACT_NAME_REQUIRED"),
    designDocumentId: nullableString(record.design_document_id ?? record.designDocumentId),
  };
}

export function parseBranch(value: unknown): VersionBranch {
  const record = asRecord(value, "VERSION_BRANCH_INVALID");
  return {
    id: requiredString(record.id, "VERSION_BRANCH_ID_REQUIRED"),
    artifactId: requiredString(record.artifact_id ?? record.artifactId, "VERSION_BRANCH_ARTIFACT_REQUIRED"),
    name: requiredString(record.name, "VERSION_BRANCH_NAME_REQUIRED"),
    baseVersionId: nullableString(record.base_version_id ?? record.baseVersionId),
    headVersionId: nullableString(record.head_version_id ?? record.headVersionId),
    createdByType: enumValue(record.created_by_type ?? record.createdByType, ["USER", "AGENT", "SYSTEM", "IMPORT"] as const, "VERSION_BRANCH_CREATOR_TYPE_INVALID"),
    createdById: nullableString(record.created_by_id ?? record.createdById),
    createdAt: requiredString(record.created_at ?? record.createdAt, "VERSION_BRANCH_CREATED_AT_REQUIRED"),
  };
}

export function parseVersionItem(value: unknown): VersionHistoryItem {
  const record = asRecord(value, "VERSION_ITEM_INVALID");
  return {
    id: requiredString(record.id, "VERSION_ID_REQUIRED"),
    artifactId: requiredString(record.artifact_id ?? record.artifactId, "VERSION_ARTIFACT_ID_REQUIRED"),
    branchId: requiredString(record.branch_id ?? record.branchId, "VERSION_BRANCH_ID_REQUIRED"),
    parentVersionId: nullableString(record.parent_version_id ?? record.parentVersionId),
    versionNumber: integer(record.version_number ?? record.versionNumber, "VERSION_NUMBER_INVALID", 1),
    status: enumValue(record.status, ["DRAFT", "READY", "APPROVED", "REJECTED", "ARCHIVED"] as const, "VERSION_STATUS_INVALID"),
    contentHash: sha256(record.content_hash ?? record.contentHash),
    designDocumentVersionId: nullableString(record.design_document_version_id ?? record.designDocumentVersionId),
    qualityScore: nullableFiniteNumber(record.quality_score ?? record.qualityScore, "VERSION_QUALITY_INVALID", 0, 1),
    constraintSnapshotHash: nullableSha256(record.constraint_snapshot_hash ?? record.constraintSnapshotHash),
    createdByType: enumValue(record.created_by_type ?? record.createdByType, ["USER", "AGENT", "SYSTEM", "IMPORT"] as const, "VERSION_CREATOR_TYPE_INVALID"),
    createdById: nullableString(record.created_by_id ?? record.createdById),
    createdAt: requiredString(record.created_at ?? record.createdAt, "VERSION_CREATED_AT_REQUIRED"),
    preview: parsePreview(record.preview ?? {}),
  };
}

function parsePreview(value: unknown): VersionPreview {
  const record = asRecord(value, "VERSION_PREVIEW_INVALID");
  return {
    mimeType: nullableString(record.mime_type ?? record.mimeType),
    width: nullableInteger(record.width, "VERSION_PREVIEW_WIDTH_INVALID", 1),
    height: nullableInteger(record.height, "VERSION_PREVIEW_HEIGHT_INVALID", 1),
    durationMs: nullableInteger(record.duration_ms ?? record.durationMs, "VERSION_PREVIEW_DURATION_INVALID", 0),
  };
}

function parseSemanticDiff(value: unknown): SemanticDiff | null {
  if (value === undefined || value === null) return null;
  const record = asRecord(value, "VERSION_SEMANTIC_DIFF_INVALID");
  return {
    nodesAdded: stringArray(record.nodes_added ?? [], "VERSION_DIFF_ADDED_INVALID"),
    nodesRemoved: stringArray(record.nodes_removed ?? [], "VERSION_DIFF_REMOVED_INVALID"),
    propertiesChanged: stringArray(record.properties_changed ?? [], "VERSION_DIFF_PROPERTIES_INVALID"),
    textChanged: stringArray(record.text_changed ?? [], "VERSION_DIFF_TEXT_INVALID"),
    geometryChanged: stringArray(record.geometry_changed ?? [], "VERSION_DIFF_GEOMETRY_INVALID"),
    assetReplaced: stringArray(record.asset_replaced ?? [], "VERSION_DIFF_ASSET_INVALID"),
    constraintsChanged: stringArray(record.constraints_changed ?? [], "VERSION_DIFF_CONSTRAINT_INVALID"),
  };
}

function parseVisualMetrics(value: unknown): Readonly<Record<string, number>> | null {
  if (value === undefined || value === null) return null;
  const record = asRecord(value, "VERSION_VISUAL_METRICS_INVALID");
  const safe: Record<string, number> = {};
  for (const [key, metric] of Object.entries(record)) {
    if (!/^[A-Za-z0-9_.-]{1,80}$/.test(key) || typeof metric !== "number" || !Number.isFinite(metric)) {
      throw new Error("VERSION_VISUAL_METRIC_INVALID");
    }
    safe[key] = metric;
  }
  return safe;
}

function asRecord(value: unknown, code: string): Record<string, unknown> { if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(code); return value as Record<string, unknown>; }
function asArray(value: unknown, code: string): unknown[] { if (!Array.isArray(value)) throw new Error(code); return value; }
function requiredString(value: unknown, code: string): string { if (typeof value !== "string" || value.trim() === "") throw new Error(code); return value; }
function nullableString(value: unknown): string | null { if (value === undefined || value === null) return null; if (typeof value !== "string") throw new Error("VERSION_OPTIONAL_STRING_INVALID"); return value; }
function requiredBoolean(value: unknown, code: string): boolean { if (typeof value !== "boolean") throw new Error(code); return value; }
function stringArray(value: unknown, code: string): string[] { const items = asArray(value, code); if (!items.every((item) => typeof item === "string")) throw new Error(code); return items as string[]; }
function integer(value: unknown, code: string, min: number): number { if (!Number.isInteger(value) || (value as number) < min) throw new Error(code); return value as number; }
function nullableInteger(value: unknown, code: string, min: number): number | null { if (value === undefined || value === null) return null; return integer(value, code, min); }
function finiteNumber(value: unknown, code: string, min: number, max: number): number { if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) throw new Error(code); return value; }
function nullableFiniteNumber(value: unknown, code: string, min: number, max: number): number | null { if (value === undefined || value === null) return null; return finiteNumber(value, code, min, max); }
function sha256(value: unknown): string { const text = requiredString(value, "VERSION_SHA_REQUIRED"); if (!/^[0-9a-f]{64}$/.test(text)) throw new Error("VERSION_SHA_INVALID"); return text; }
function nullableSha256(value: unknown): string | null { if (value === undefined || value === null) return null; return sha256(value); }
function gitSha(value: unknown): string { const text = requiredString(value, "VERSION_GIT_SHA_REQUIRED"); if (!/^[0-9a-f]{40}$/.test(text)) throw new Error("VERSION_GIT_SHA_INVALID"); return text; }
function enumValue<const T extends readonly string[]>(value: unknown, allowed: T, code: string): T[number] { if (typeof value !== "string" || !(allowed as readonly string[]).includes(value)) throw new Error(code); return value as T[number]; }
