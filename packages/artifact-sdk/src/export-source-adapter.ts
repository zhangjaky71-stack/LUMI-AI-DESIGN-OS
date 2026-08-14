import type { CompiledSceneSnapshot, CompileResult } from "../../canvas-sdk/src/index";
import type { DesignDocument } from "../../design-ir/src/index";
import { compilerProvenanceFromSnapshot } from "./compiler-bridge";
import { ArtifactEngine } from "./engine";
import type { ExportSourcePort, ExportSourceSnapshot, ExportSpec } from "./export-engine-types";

export interface ExactDesignVersionPort {
  loadExact(args: {
    readonly organization_id: string;
    readonly project_id: string;
    readonly design_document_version_id: string;
  }): Promise<DesignDocument>;
}

export interface ExactExportCompilerPort {
  fullCompile(document: DesignDocument, useCache?: boolean): Promise<CompileResult>;
}

export interface ExportSourceMetadataPort {
  rightsSummary(args: { readonly organization_id: string; readonly artifact_version_id: string }): Promise<Readonly<Record<string, unknown>>>;
  modelRefs(args: { readonly organization_id: string; readonly artifact_version_id: string }): Promise<readonly string[]>;
  provenanceRefs(args: { readonly organization_id: string; readonly artifact_version_id: string }): Promise<readonly string[]>;
  projectSnapshot?(args: { readonly organization_id: string; readonly project_id: string }): Promise<Readonly<Record<string, unknown>> | undefined>;
}

const EPHEMERAL_KEY = /(?:^|_)(?:uri|url)$/i;

function durableClone(value: unknown, depth = 0): unknown {
  if (depth > 32) throw new Error("EXPORT_SOURCE_SNAPSHOT_TOO_DEEP");
  if (value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) return value.map((item) => durableClone(item, depth + 1));
  if (typeof value !== "object") throw new Error("EXPORT_SOURCE_SNAPSHOT_VALUE_UNSUPPORTED");
  const output: Record<string, unknown> = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    if (EPHEMERAL_KEY.test(key)) continue;
    output[key] = durableClone(child, depth + 1);
  }
  return output;
}

function durableDesignDocument(document: DesignDocument): DesignDocument {
  return durableClone(document) as DesignDocument;
}

function durableRenderPlan(snapshot: CompiledSceneSnapshot): unknown {
  return {
    compiler_version: snapshot.render_plan.compiler_version,
    document_id: snapshot.render_plan.document_id,
    items: snapshot.render_plan.items.map((item) => ({
      id: item.id,
      kind: item.kind,
      parent_id: item.parent_id,
      visible: item.visible,
      z_order: item.z_order,
      world_matrix: { ...item.world_matrix },
      local_bounds: { ...item.local_bounds },
      world_bounds: { ...item.world_bounds },
      resolved_style: { ...item.resolved_style },
      ...(item.resolved_text ? {
        resolved_text: {
          content: item.resolved_text.content,
          ...(item.resolved_text.metrics ? { metrics: { ...item.resolved_text.metrics } } : {}),
          ...(item.resolved_text.font ? {
            font: {
              family: item.resolved_text.font.family,
              version: item.resolved_text.font.version,
              ...(item.resolved_text.font.weight !== undefined ? { weight: item.resolved_text.font.weight } : {}),
              ...(item.resolved_text.font.style !== undefined ? { style: item.resolved_text.font.style } : {}),
              status: item.resolved_text.font.status,
            },
          } : {}),
        },
      } : {}),
      ...(item.resolved_resource ? {
        resolved_resource: {
          asset_id: item.resolved_resource.asset_id,
          version: item.resolved_resource.version,
          variant: item.resolved_resource.variant,
          status: item.resolved_resource.status,
          ...(item.resolved_resource.mime_type ? { mime_type: item.resolved_resource.mime_type } : {}),
          ...(item.resolved_resource.width !== undefined ? { width: item.resolved_resource.width } : {}),
          ...(item.resolved_resource.height !== undefined ? { height: item.resolved_resource.height } : {}),
        },
      } : {}),
      interaction_flags: { ...item.interaction_flags },
      ...(item.clip_id ? { clip_id: item.clip_id } : {}),
      ...(item.mask_id ? { mask_id: item.mask_id } : {}),
      placeholder: item.placeholder,
    })),
  };
}

export class ArtifactEngineExportSource implements ExportSourcePort {
  readonly #artifacts: ArtifactEngine;
  readonly #designs: ExactDesignVersionPort;
  readonly #compiler: ExactExportCompilerPort;
  readonly #metadata: ExportSourceMetadataPort;

  constructor(args: {
    readonly artifacts: ArtifactEngine;
    readonly designs: ExactDesignVersionPort;
    readonly compiler: ExactExportCompilerPort;
    readonly metadata: ExportSourceMetadataPort;
  }) {
    this.#artifacts = args.artifacts;
    this.#designs = args.designs;
    this.#compiler = args.compiler;
    this.#metadata = args.metadata;
  }

  async resolveExactSnapshot(spec: ExportSpec): Promise<ExportSourceSnapshot> {
    const version = this.#artifacts.versions.get(spec.artifact_version_id);
    if (!version) throw new Error("EXPORT_SOURCE_ARTIFACT_VERSION_NOT_FOUND");
    const artifact = this.#artifacts.artifacts.get(version.artifact_id);
    if (!artifact) throw new Error("EXPORT_SOURCE_ARTIFACT_NOT_FOUND");
    if (version.organization_id !== spec.organization_id || artifact.organization_id !== spec.organization_id || artifact.project_id !== spec.project_id) {
      throw new Error("EXPORT_SOURCE_SCOPE_MISMATCH");
    }
    if (version.design_document_version_id !== spec.design_document_version_id) {
      throw new Error("EXPORT_SOURCE_DESIGN_VERSION_NOT_EXACT");
    }
    const document = await this.#designs.loadExact({
      organization_id: spec.organization_id,
      project_id: spec.project_id,
      design_document_version_id: spec.design_document_version_id,
    });
    const compiled = await this.#compiler.fullCompile(document, false);
    if (!compiled.ok) {
      const codes = compiled.diagnostics.map((item) => item.code).join(",");
      throw new Error(`EXPORT_SOURCE_COMPILE_FAILED:${codes}`);
    }
    const snapshot = compiled.snapshot;
    const compilerProvenance = compilerProvenanceFromSnapshot(snapshot);
    if (snapshot.document_id !== document.document_id || compilerProvenance.document_id !== document.document_id) {
      throw new Error("EXPORT_COMPILER_DOCUMENT_IDENTITY_MISMATCH");
    }
    const rightsSummary = await this.#metadata.rightsSummary({ organization_id: spec.organization_id, artifact_version_id: version.id });
    const modelRefs = await this.#metadata.modelRefs({ organization_id: spec.organization_id, artifact_version_id: version.id });
    const provenanceRefs = await this.#metadata.provenanceRefs({ organization_id: spec.organization_id, artifact_version_id: version.id });
    const projectSnapshot = this.#metadata.projectSnapshot
      ? await this.#metadata.projectSnapshot({ organization_id: spec.organization_id, project_id: spec.project_id })
      : undefined;
    return {
      organization_id: spec.organization_id,
      project_id: spec.project_id,
      artifact_id: artifact.id,
      artifact_version_id: version.id,
      design_document_version_id: spec.design_document_version_id,
      content_hash: version.content_hash,
      constraint_snapshot_hash: version.constraint_snapshot_hash,
      compiler_provenance: compilerProvenance,
      design_document: durableDesignDocument(document),
      render_plan: durableRenderPlan(snapshot),
      brand_rule_set_version: version.brand_rule_set_version ?? null,
      rights_summary: rightsSummary,
      model_refs: [...new Set(modelRefs)].sort(),
      source_provenance_refs: [...new Set(provenanceRefs)].sort(),
      ...(projectSnapshot ? { project_snapshot: projectSnapshot } : {}),
    };
  }
}
