import type {
  Artifact,
  ArtifactBranch,
  ArtifactLineageEdge,
  ArtifactProvenance,
  ArtifactType,
  ArtifactVersion,
  ArtifactVersionStatus,
  CompilerArtifactProvenance,
} from "@lumi/artifact-sdk";

export type { Artifact, ArtifactBranch, ArtifactLineageEdge, ArtifactProvenance, ArtifactVersion };

export type VersionPreviewKind = "DESIGN_IR" | "RASTER";
export type CompareViewMode = "SIDE_BY_SIDE" | "OVERLAY" | "WIPE";
export type SemanticChangeKind = "TEXT" | "STYLE" | "LAYOUT" | "ASSET" | "IDENTITY" | "OTHER";
export type VersionNoticeKind = "INFO" | "WARNING" | "CONFLICT";

export interface ArtifactVersionOption {
  readonly artifact_id: string;
  readonly title: string;
  readonly type: ArtifactType;
  readonly branch_count: number;
  readonly version_count: number;
  readonly head_version_id: string | null;
}

export interface VersionSemanticChange {
  readonly id: string;
  readonly kind: SemanticChangeKind;
  readonly label: string;
  readonly node_id: string | null;
  readonly node_name: string | null;
  readonly property: string;
  readonly before: string | number | boolean | null;
  readonly after: string | number | boolean | null;
  readonly protected_identity: boolean;
}

export interface VersionPreview {
  readonly kind: VersionPreviewKind;
  readonly label: string;
  readonly width: number;
  readonly height: number;
  readonly background: string;
  readonly accent: string;
  readonly secondary: string;
  readonly image_asset_id: string | null;
}

export interface VersionApprovalSummary {
  readonly status: ArtifactVersionStatus;
  readonly approved_by: string | null;
  readonly approved_at: string | null;
  readonly validation_label: string | null;
}

export interface VersionQualitySummary {
  readonly score: number | null;
  readonly label: string;
  readonly checks: readonly string[];
}

export interface VersionTimelineItem {
  readonly version: ArtifactVersion;
  readonly branch_name: string;
  readonly semantic_changes: readonly VersionSemanticChange[];
  readonly preview: VersionPreview;
  readonly approval: VersionApprovalSummary;
  readonly quality: VersionQualitySummary;
  readonly safe_change_summary: string;
  readonly lineage_labels: readonly string[];
}

export interface SafeVersionProvenance {
  readonly artifact_version_id: string;
  readonly created_by_type: ArtifactVersion["created_by_type"];
  readonly created_by_id: string;
  readonly model: string | null;
  readonly provider: string | null;
  readonly agent_run_id: string | null;
  readonly task_id: string | null;
  readonly generation_id: string | null;
  readonly recipe_version: string | null;
  readonly skill_versions: Readonly<Record<string, string>>;
  readonly input_asset_ids: readonly string[];
  readonly input_artifact_version_ids: readonly string[];
  readonly brand_rule_set_version: string | null;
  readonly constraint_snapshot_hash: string;
  readonly prompt_hash: string | null;
  readonly prompt_template_version: string | null;
  readonly code_git_sha: string;
  readonly compiler: CompilerArtifactProvenance | null;
  readonly quality_checks: readonly string[];
}

export interface VersionWorkspaceSnapshot {
  readonly project_id: string;
  readonly project_name: string;
  readonly revision: number;
  readonly artifact_options: readonly ArtifactVersionOption[];
  readonly active_artifact: Artifact;
  readonly branches: readonly ArtifactBranch[];
  readonly versions: readonly VersionTimelineItem[];
  readonly lineage: readonly ArtifactLineageEdge[];
  readonly active_branch_id: string;
  readonly head_version_id: string | null;
  readonly can_view_provenance: boolean;
  readonly concurrent_head_version_id: string | null;
  readonly notice: {
    readonly kind: VersionNoticeKind;
    readonly message: string;
  } | null;
}

export interface VersionCompareResult {
  readonly artifact_id: string;
  readonly from_version_id: string;
  readonly to_version_id: string;
  readonly kind: VersionPreviewKind;
  readonly before: VersionTimelineItem;
  readonly after: VersionTimelineItem;
  readonly semantic_changes: readonly VersionSemanticChange[];
  readonly exact: true;
}

export interface RestoreVersionInput {
  readonly artifact_id: string;
  readonly branch_id: string;
  readonly source_version_id: string;
  readonly expected_head_version_id: string | null;
}

export interface ForkVersionInput {
  readonly artifact_id: string;
  readonly source_version_id: string;
  readonly name: string;
}

export interface VersionsBootstrapSeed {
  readonly project_id: string;
  readonly project_name: string;
  readonly active_artifact_id: string;
  readonly artifacts: readonly Artifact[];
  readonly branches: readonly ArtifactBranch[];
  readonly versions: readonly ArtifactVersion[];
  readonly lineage: readonly ArtifactLineageEdge[];
  readonly provenance: readonly ArtifactProvenance[];
  readonly semantic_changes: Readonly<Record<string, readonly VersionSemanticChange[]>>;
  readonly previews: Readonly<Record<string, VersionPreview>>;
  readonly approval: Readonly<Record<string, VersionApprovalSummary>>;
  readonly quality: Readonly<Record<string, VersionQualitySummary>>;
  readonly safe_summaries: Readonly<Record<string, string>>;
  readonly provenance_access: boolean;
}

export interface VersionsBootstrap {
  readonly mode: "http" | "e2e";
  readonly seed: VersionsBootstrapSeed | null;
}
