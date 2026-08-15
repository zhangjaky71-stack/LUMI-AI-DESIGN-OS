import type {
  Artifact,
  ArtifactBranch,
  ArtifactLineageEdge,
  ArtifactProvenance,
  ArtifactVersion,
} from "@lumi/artifact-sdk";
import type {
  VersionApprovalSummary,
  VersionPreview,
  VersionQualitySummary,
  VersionsBootstrap,
  VersionsBootstrapSeed,
  VersionSemanticChange,
} from "./types";

const H = {
  a: "a".repeat(64),
  b: "b".repeat(64),
  c: "c".repeat(64),
  d: "d".repeat(64),
  e: "e".repeat(64),
  f: "f".repeat(64),
  zero: "0".repeat(64),
};

function designArtifact(projectId: string): Artifact {
  return {
    id: "artifact-campaign-canvas",
    organization_id: "org-lumi",
    project_id: projectId,
    type: "DESIGN_DOCUMENT",
    title: "Summer Campaign Canvas",
    archived: false,
  };
}

function rasterArtifact(projectId: string): Artifact {
  return {
    id: "artifact-hero-raster",
    organization_id: "org-lumi",
    project_id: projectId,
    type: "RASTER_IMAGE",
    title: "Hero Visual Render",
    archived: false,
  };
}

function version(
  id: string,
  artifactId: string,
  branchId: string,
  number: number,
  parent: string | null,
  status: ArtifactVersion["status"],
  createdByType: ArtifactVersion["created_by_type"],
  createdById: string,
  createdAt: string,
  contentHash: string,
  qualityScore: number | null,
): ArtifactVersion {
  return {
    id,
    organization_id: "org-lumi",
    artifact_id: artifactId,
    branch_id: branchId,
    parent_version_id: parent,
    schema_version: "design-ir@1",
    version_number: number,
    status,
    content_hash: contentHash,
    constraint_snapshot_hash: H.zero,
    created_by_type: createdByType,
    created_by_id: createdById,
    created_at: createdAt,
    primary_file_id: `file-${id}`,
    design_document_version_id: artifactId === "artifact-campaign-canvas" ? `document-version-${number}` : null,
    brand_rule_set_version: "1.0.0",
    identity_validation_snapshot_id: "identity-snapshot-summer-product",
    quality_score: qualityScore,
  };
}

function provenance(versionId: string, options: {
  createdBy: "USER" | "AGENT";
  model?: string;
  provider?: string;
  run?: string;
  task?: string;
  promptHash?: string;
  recipe?: string;
  inputs?: readonly string[];
}): ArtifactProvenance {
  return {
    artifact_version_id: versionId,
    organization_id: "org-lumi",
    constraint_snapshot_hash: H.zero,
    code_git_sha: "c6ffd62d09a64a4cf839f6971895a65e8602060d",
    compiler: {
      compiler_version: "canvas-compiler@1.0.0",
      document_id: "document:project-summer-launch",
      schema_version: "design-ir@1",
      document_version: Number(versionId.match(/v(\d+)/)?.[1] ?? 1),
      resource_versions: { "brand-assets": "assets-1.0.0" },
      font_versions: { "font-heading": "asset-font-lumi-grotesk" },
      compile_hash: H.f,
    },
    brand_rule_set_version: "1.0.0",
    identity_validation_snapshot_id: "identity-snapshot-summer-product",
    ...(options.run ? { agent_run_id: options.run } : {}),
    ...(options.task ? { task_id: options.task } : {}),
    ...(options.provider ? { provider: options.provider } : {}),
    ...(options.model ? { model: options.model } : {}),
    ...(options.promptHash ? { prompt_hash: options.promptHash } : {}),
    prompt_template_version: options.createdBy === "AGENT" ? "visual-direction@3" : "manual-edit@1",
    input_asset_ids: ["asset-lumi-product", "asset-logo-primary"],
    input_artifact_version_ids: options.inputs ?? [],
    design_ir_schema_version: "design-ir@1",
    ...(options.recipe ? { recipe_version: options.recipe } : {}),
    skill_versions: options.createdBy === "AGENT" ? { composition: "2.1.0", brand: "1.4.2" } : {},
  };
}

export function versionsSeed(projectId: string): VersionsBootstrapSeed {
  const design = designArtifact(projectId);
  const raster = rasterArtifact(projectId);
  const designMain: ArtifactBranch = {
    id: "branch-design-main",
    organization_id: "org-lumi",
    artifact_id: design.id,
    name: "main",
    base_version_id: "design-v1",
    head_version_id: "design-v4",
    created_by: "user:owner",
  };
  const rasterMain: ArtifactBranch = {
    id: "branch-raster-main",
    organization_id: "org-lumi",
    artifact_id: raster.id,
    name: "main",
    base_version_id: "raster-v1",
    head_version_id: "raster-v3",
    created_by: "agent:visual",
  };
  const versions: ArtifactVersion[] = [
    version("design-v1", design.id, designMain.id, 1, null, "READY", "USER", "user:owner", "2026-08-14T08:10:00.000Z", H.a, 82),
    version("design-v2", design.id, designMain.id, 2, "design-v1", "APPROVED", "AGENT", "agent:designer", "2026-08-14T08:42:00.000Z", H.b, 94),
    version("design-v3", design.id, designMain.id, 3, "design-v2", "DRAFT", "USER", "user:owner", "2026-08-14T09:18:00.000Z", H.c, null),
    version("design-v4", design.id, designMain.id, 4, "design-v3", "READY", "AGENT", "agent:designer", "2026-08-15T01:12:00.000Z", H.d, 91),
    version("raster-v1", raster.id, rasterMain.id, 1, null, "READY", "AGENT", "agent:renderer", "2026-08-14T08:50:00.000Z", H.a, 88),
    version("raster-v2", raster.id, rasterMain.id, 2, "raster-v1", "APPROVED", "USER", "user:owner", "2026-08-14T09:02:00.000Z", H.e, 96),
    version("raster-v3", raster.id, rasterMain.id, 3, "raster-v2", "DRAFT", "AGENT", "agent:renderer", "2026-08-15T01:15:00.000Z", H.f, null),
  ];
  const lineage: ArtifactLineageEdge[] = [
    {
      id: "edge-design-v1-v2",
      organization_id: "org-lumi",
      from_version_id: "design-v1",
      to_version_id: "design-v2",
      type: "EDITED_FROM",
      metadata: { operation: "AGENT_EDIT" },
    },
    {
      id: "edge-design-v2-v3",
      organization_id: "org-lumi",
      from_version_id: "design-v2",
      to_version_id: "design-v3",
      type: "EDITED_FROM",
      metadata: { operation: "USER_EDIT" },
    },
    {
      id: "edge-design-v3-v4",
      organization_id: "org-lumi",
      from_version_id: "design-v3",
      to_version_id: "design-v4",
      type: "EDITED_FROM",
      metadata: { operation: "AGENT_EDIT" },
    },
    {
      id: "edge-raster-v1-v2",
      organization_id: "org-lumi",
      from_version_id: "raster-v1",
      to_version_id: "raster-v2",
      type: "EDITED_FROM",
    },
    {
      id: "edge-raster-v2-v3",
      organization_id: "org-lumi",
      from_version_id: "raster-v2",
      to_version_id: "raster-v3",
      type: "EDITED_FROM",
    },
  ];

  const changes: Record<string, readonly VersionSemanticChange[]> = {
    "design-v1": [
      { id: "c-v1-create", kind: "OTHER", label: "Initial campaign composition", node_id: null, node_name: null, property: "document", before: null, after: "created", protected_identity: false },
    ],
    "design-v2": [
      { id: "c-v2-title", kind: "TEXT", label: "Headline size 68→58", node_id: "node-headline", node_name: "Headline", property: "font_size", before: 68, after: 58, protected_identity: false },
      { id: "c-v2-product", kind: "IDENTITY", label: "Product identity unchanged", node_id: "node-hero-product", node_name: "Hero Product", property: "asset_id", before: "asset-lumi-product", after: "asset-lumi-product", protected_identity: true },
    ],
    "design-v3": [
      { id: "c-v3-bg", kind: "STYLE", label: "Background warm neutral→charcoal", node_id: "frame-feed", node_name: "Feed / 4:5", property: "fill", before: "#F3EBDD", after: "#1C1917", protected_identity: false },
    ],
    "design-v4": [
      { id: "c-v4-offer", kind: "LAYOUT", label: "Offer badge moved +24px", node_id: "node-offer", node_name: "Offer Badge", property: "x", before: 920, after: 944, protected_identity: false },
      { id: "c-v4-title", kind: "TEXT", label: "Headline copy refined", node_id: "node-headline", node_name: "Headline", property: "text", before: "SUMMER DROP", after: "SUMMER FLAVOR DROP", protected_identity: false },
    ],
    "raster-v1": [
      { id: "r1", kind: "OTHER", label: "Initial render", node_id: null, node_name: null, property: "render", before: null, after: "v1", protected_identity: false },
    ],
    "raster-v2": [
      { id: "r2", kind: "STYLE", label: "Lighting softened", node_id: null, node_name: null, property: "lighting", before: "hard side light", after: "soft daylight", protected_identity: false },
    ],
    "raster-v3": [
      { id: "r3", kind: "STYLE", label: "Background shifted darker", node_id: null, node_name: null, property: "background", before: "warm oat", after: "charcoal", protected_identity: false },
    ],
  };
  const previews: Record<string, VersionPreview> = {
    "design-v1": { kind: "DESIGN_IR", label: "4:5 campaign · oat", width: 1080, height: 1350, background: "#F3EBDD", accent: "#D9A441", secondary: "#1C1917", image_asset_id: "asset-lumi-product" },
    "design-v2": { kind: "DESIGN_IR", label: "4:5 campaign · approved", width: 1080, height: 1350, background: "#F3EBDD", accent: "#D9A441", secondary: "#1C1917", image_asset_id: "asset-lumi-product" },
    "design-v3": { kind: "DESIGN_IR", label: "4:5 campaign · dark draft", width: 1080, height: 1350, background: "#1C1917", accent: "#D9A441", secondary: "#F3EBDD", image_asset_id: "asset-lumi-product" },
    "design-v4": { kind: "DESIGN_IR", label: "4:5 campaign · current", width: 1080, height: 1350, background: "#1C1917", accent: "#D9A441", secondary: "#F3EBDD", image_asset_id: "asset-lumi-product" },
    "raster-v1": { kind: "RASTER", label: "Render v1", width: 1080, height: 1350, background: "#EEE4D4", accent: "#D9A441", secondary: "#2D2926", image_asset_id: "asset-render-v1" },
    "raster-v2": { kind: "RASTER", label: "Render v2 · approved", width: 1080, height: 1350, background: "#F3EBDD", accent: "#E4B85D", secondary: "#1C1917", image_asset_id: "asset-render-v2" },
    "raster-v3": { kind: "RASTER", label: "Render v3 · dark", width: 1080, height: 1350, background: "#201D1B", accent: "#D9A441", secondary: "#F3EBDD", image_asset_id: "asset-render-v3" },
  };
  const approval: Record<string, VersionApprovalSummary> = Object.fromEntries(
    versions.map((item) => [
      item.id,
      {
        status: item.status,
        approved_by: item.status === "APPROVED" ? "user:creative-director" : null,
        approved_at: item.status === "APPROVED" ? "2026-08-14T09:05:00.000Z" : null,
        validation_label: item.status === "APPROVED" ? "Brand + identity + visual QA passed" : null,
      },
    ]),
  );
  const quality: Record<string, VersionQualitySummary> = Object.fromEntries(
    versions.map((item) => [
      item.id,
      {
        score: item.quality_score ?? null,
        label: item.quality_score == null ? "Not scored" : item.quality_score >= 94 ? "Excellent" : item.quality_score >= 88 ? "Ready" : "Review",
        checks: item.status === "APPROVED" ? ["Brand compliance", "Identity lock", "Visual critic"] : ["Constraint preflight", "Identity lock"],
      },
    ]),
  );
  const safeSummaries: Record<string, string> = {
    "design-v1": "Initial structured campaign composition.",
    "design-v2": "Typography refined while protected product identity stayed unchanged.",
    "design-v3": "User explored a darker background direction.",
    "design-v4": "Agent refined offer placement and headline copy.",
    "raster-v1": "Initial raster render.",
    "raster-v2": "Lighting softened and approved for campaign use.",
    "raster-v3": "Exploratory dark-background render.",
  };
  const provenanceRows: ArtifactProvenance[] = [
    provenance("design-v1", { createdBy: "USER" }),
    provenance("design-v2", { createdBy: "AGENT", model: "gpt-image-design-router", provider: "primary-image-provider", run: "run-summer-17", task: "task-composition", promptHash: H.b, recipe: "campaign-kv@4", inputs: ["design-v1"] }),
    provenance("design-v3", { createdBy: "USER", inputs: ["design-v2"] }),
    provenance("design-v4", { createdBy: "AGENT", model: "gpt-image-design-router", provider: "backup-image-provider", run: "run-summer-21", task: "task-layout-repair", promptHash: H.d, recipe: "campaign-kv@4", inputs: ["design-v3"] }),
    provenance("raster-v1", { createdBy: "AGENT", model: "renderer-v2", provider: "lumi-render", run: "run-summer-17", task: "task-render", promptHash: H.a, recipe: "render@2", inputs: ["design-v2"] }),
    provenance("raster-v2", { createdBy: "USER", inputs: ["raster-v1"] }),
    provenance("raster-v3", { createdBy: "AGENT", model: "renderer-v2", provider: "lumi-render", run: "run-summer-21", task: "task-render", promptHash: H.f, recipe: "render@2", inputs: ["design-v4"] }),
  ];

  return {
    project_id: projectId,
    project_name: projectId === "project-summer-launch" ? "夏季新品发布" : "Version History Project",
    active_artifact_id: design.id,
    artifacts: [design, raster],
    branches: [designMain, rasterMain],
    versions,
    lineage,
    provenance: provenanceRows,
    semantic_changes: changes,
    previews,
    approval,
    quality,
    safe_summaries: safeSummaries,
    provenance_access: projectId !== "project-provenance-denied",
  };
}

export function getVersionsBootstrap(projectId: string): VersionsBootstrap {
  const e2e = process.env.NODE_ENV !== "production" && process.env.LUMI_VERSIONS_E2E === "1";
  return e2e ? { mode: "e2e", seed: versionsSeed(projectId) } : { mode: "http", seed: null };
}
