import {
  canonicalSha256,
  canonicalStringify,
  getDocumentVersion,
  semanticDiff,
  validateDocument,
  type DesignDocument,
  type IrValidationIssue,
} from "../../design-ir/src/index";
import { CanvasCompilerCache, canvasCompilerCacheKey } from "./compiler-cache";
import { planCompilerDirtyNodes } from "./compiler-dirty";
import {
  DeterministicTextMeasurer,
  DocumentCompilerAssetResolver,
  DocumentCompilerFontResolver,
  DocumentCompilerStyleResolver,
} from "./compiler-resolvers";
import {
  CANVAS_COMPILER_VERSION,
  type CanvasCompileProvenance,
  type CanvasCompilerOptions,
  type CanvasRenderPlan,
  type CanvasRenderPlanItem,
  type CompileDiagnostic,
  type CompilePatch,
  type CompileResult,
  type CompiledSceneNode,
  type CompiledSceneSnapshot,
  type CompilerAssetResolver,
  type CompilerFontResolver,
  type CompilerResourceVariant,
  type CompilerStyleResolver,
  type CompilerTextMeasurer,
  type IncrementalCompileRequest,
  type IncrementalCompileResult,
  type ResolvedCompilerFont,
  type ResolvedCompilerResource,
} from "./compiler-types";
import {
  projectDesignDocument,
  type CanvasNodeDiagnostic,
  type CanvasSceneNode,
} from "./ir-scene";

function metadataString(node: CanvasSceneNode, key: string): string | null {
  const value = node.metadata[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function compileDiagnosticFromIr(issue: IrValidationIssue): CompileDiagnostic {
  const code = issue.code === "IR_VERSION_UNSUPPORTED" ? "SCHEMA_UNSUPPORTED" : "STRUCTURAL_INVALID";
  return {
    code,
    severity: "ERROR",
    message: issue.message,
    pointer: issue.pointer,
    ...(issue.node_id ? { node_id: issue.node_id } : {}),
    source: issue.code,
  };
}

function fatalValidationIssue(issue: IrValidationIssue): boolean {
  return (
    issue.code === "IR_GRAPH_CYCLE" ||
    issue.code === "IR_VERSION_UNSUPPORTED" ||
    issue.pointer === "/root_id" ||
    issue.pointer === "/document_id"
  );
}

function sceneDiagnostic(value: CanvasNodeDiagnostic): CompileDiagnostic {
  return {
    code: value.code === "UNSUPPORTED_KIND" ? "NODE_PLACEHOLDER" : "IR_DIAGNOSTIC",
    severity: value.code === "CYCLE" ? "ERROR" : "WARNING",
    message: value.detail ?? value.code,
    node_id: value.node_id,
    source: value.code,
  };
}

function interactionFlags(node: CanvasSceneNode) {
  const guide = node.kind === "GUIDE";
  const root = node.kind === "DOCUMENT_ROOT";
  return {
    selectable: !root,
    transformable: !root && !guide && !node.locked,
    hit_testable: !root && node.visible,
    editable: node.kind === "TEXT" && !node.locked,
  } as const;
}

function pendingResource(assetId: string, variant: CompilerResourceVariant): ResolvedCompilerResource {
  return {
    asset_id: assetId,
    variant,
    version: "unresolved",
    status: "PENDING",
    fingerprint: canonicalStringify({ asset_id: assetId, variant, version: "unresolved" }),
  };
}

function renderPlanItem(node: CompiledSceneNode): CanvasRenderPlanItem {
  return {
    id: node.id,
    kind: node.kind,
    parent_id: node.parent_id,
    z_order: node.paint_order,
    visible: node.visible,
    local_matrix: node.local_matrix,
    world_matrix: node.world_matrix,
    local_bounds: node.local_bounds,
    world_bounds: node.world_bounds,
    resolved_style: node.resolved_style,
    interaction_flags: node.interaction_flags,
    placeholder: node.placeholder,
    ...(node.resolved_text ? { resolved_text: node.resolved_text } : {}),
    ...(node.resolved_resource ? { resolved_resource: node.resolved_resource } : {}),
    ...(node.clip_id ? { clip_id: node.clip_id } : {}),
    ...(node.mask_id ? { mask_id: node.mask_id } : {}),
  };
}

function makeRenderPlan(
  compilerVersion: string,
  documentId: string,
  paintOrder: readonly string[],
  nodes: ReadonlyMap<string, CompiledSceneNode>,
): CanvasRenderPlan {
  return {
    compiler_version: compilerVersion,
    document_id: documentId,
    items: paintOrder
      .map((id) => nodes.get(id))
      .filter((node): node is CompiledSceneNode => Boolean(node))
      .map(renderPlanItem),
  };
}

function hashableResource(resource: ResolvedCompilerResource | undefined): unknown {
  if (!resource) return null;
  return {
    asset_id: resource.asset_id,
    variant: resource.variant,
    version: resource.version,
    status: resource.status,
    fingerprint: resource.fingerprint,
    mime_type: resource.mime_type ?? null,
    width: resource.width ?? null,
    height: resource.height ?? null,
  };
}

function hashableFont(font: ResolvedCompilerFont | undefined): unknown {
  if (!font) return null;
  return {
    font_ref: font.font_ref,
    family: font.family,
    version: font.version,
    status: font.status,
    style: font.style ?? null,
    weight: font.weight ?? null,
    fingerprint: font.fingerprint,
  };
}

function hashablePlan(snapshot: Omit<CompiledSceneSnapshot, "provenance">): unknown {
  return {
    compiler_version: snapshot.compiler_version,
    document_id: snapshot.document_id,
    schema_version: snapshot.schema_version,
    root_id: snapshot.root_id,
    paint_order: snapshot.paint_order,
    items: snapshot.render_plan.items.map((item) => ({
      ...item,
      resolved_resource: item.resolved_resource
        ? hashableResource(item.resolved_resource)
        : null,
      resolved_text: item.resolved_text
        ? {
            content: item.resolved_text.content,
            font_ref: item.resolved_text.font_ref ?? null,
            font: hashableFont(item.resolved_text.font),
            metrics: item.resolved_text.metrics ?? null,
          }
        : null,
    })),
  };
}

function resourceVersions(nodes: ReadonlyMap<string, CompiledSceneNode>): Record<string, string> {
  const versions: Record<string, string> = {};
  for (const node of nodes.values()) {
    const resource = node.resolved_resource;
    if (resource) versions[resource.asset_id] = resource.version;
  }
  return Object.fromEntries(Object.entries(versions).sort(([a], [b]) => a.localeCompare(b)));
}

function fontVersions(nodes: ReadonlyMap<string, CompiledSceneNode>): Record<string, string> {
  const versions: Record<string, string> = {};
  for (const node of nodes.values()) {
    const font = node.resolved_text?.font;
    if (font) versions[font.font_ref] = font.version;
  }
  return Object.fromEntries(Object.entries(versions).sort(([a], [b]) => a.localeCompare(b)));
}

function sameNode(left: CompiledSceneNode | undefined, right: CompiledSceneNode): boolean {
  return Boolean(left && canonicalStringify(left) === canonicalStringify(right));
}

export class CanvasCompiler {
  readonly #compilerVersion: string;
  readonly #variant: CompilerResourceVariant;
  readonly #assetResolver: CompilerAssetResolver;
  readonly #fontResolver: CompilerFontResolver;
  readonly #styleResolver: CompilerStyleResolver;
  readonly #textMeasurer: CompilerTextMeasurer;
  readonly #cache: CanvasCompilerCache;

  constructor(options: CanvasCompilerOptions = {}, cache = new CanvasCompilerCache()) {
    this.#compilerVersion = options.compiler_version ?? CANVAS_COMPILER_VERSION;
    this.#variant = options.resource_variant ?? "preview";
    this.#assetResolver = options.asset_resolver ?? new DocumentCompilerAssetResolver();
    this.#fontResolver = options.font_resolver ?? new DocumentCompilerFontResolver();
    this.#styleResolver = options.style_resolver ?? new DocumentCompilerStyleResolver();
    this.#textMeasurer = options.text_measurer ?? new DeterministicTextMeasurer();
    this.#cache = cache;
  }

  get version(): string {
    return this.#compilerVersion;
  }

  compileStructure(document: DesignDocument): CompileResult {
    const validation = validateDocument(document);
    const validationDiagnostics = validation.issues.map(compileDiagnosticFromIr);
    if (validation.issues.some(fatalValidationIssue)) {
      return { ok: false, diagnostics: validationDiagnostics };
    }

    const base = projectDesignDocument(document);
    const diagnostics: CompileDiagnostic[] = [
      ...validationDiagnostics,
      ...base.diagnostics.map(sceneDiagnostic),
    ];
    const nodes = new Map<string, CompiledSceneNode>();

    for (const id of base.paint_order) {
      const node = base.nodes.get(id);
      const source = document.nodes[id];
      if (!node || !source) continue;
      const styleResult = this.#styleResolver.resolveStyle(document, source.style_refs ?? []);
      for (const missing of styleResult.missing_refs) {
        diagnostics.push({
          code: "STYLE_TOKEN_MISSING",
          severity: "WARNING",
          message: `Style token ${missing} is missing`,
          node_id: id,
          source: missing,
        });
      }
      const fontRef = metadataString(node, "font_asset_id") ?? metadataString(node, "font_ref") ?? undefined;
      const clipId = metadataString(node, "clip_id") ?? undefined;
      const maskId = metadataString(node, "mask_id") ?? undefined;
      const placeholder = base.diagnostics.some(
        (value) => value.node_id === id && value.code === "UNSUPPORTED_KIND",
      );
      const resolvedResource = node.asset_id ? pendingResource(node.asset_id, this.#variant) : undefined;
      const resolvedText = node.kind === "TEXT"
        ? {
            content: node.content ?? "",
            ...(fontRef ? { font_ref: fontRef } : {}),
          }
        : undefined;
      const renderKey = canonicalStringify({
        compiler_version: this.#compilerVersion,
        source_render_key: node.render_key,
        resolved_style: styleResult.style,
        font_ref: fontRef ?? null,
        resource: hashableResource(resolvedResource),
        clip_id: clipId ?? null,
        mask_id: maskId ?? null,
        placeholder,
      });
      nodes.set(id, {
        ...node,
        render_key: renderKey,
        resolved_style: styleResult.style,
        interaction_flags: interactionFlags(node),
        placeholder,
        ...(resolvedText ? { resolved_text: resolvedText } : {}),
        ...(resolvedResource ? { resolved_resource: resolvedResource } : {}),
        ...(clipId ? { clip_id: clipId } : {}),
        ...(maskId ? { mask_id: maskId } : {}),
      });
    }

    const renderPlan = makeRenderPlan(
      this.#compilerVersion,
      document.document_id,
      base.paint_order,
      nodes,
    );
    const provenance: CanvasCompileProvenance = {
      compiler_version: this.#compilerVersion,
      document_id: document.document_id,
      schema_version: document.schema_version,
      document_version: getDocumentVersion(document),
      resource_versions: {},
      font_versions: {},
    };
    const snapshot: CompiledSceneSnapshot = {
      ...base,
      compiler_version: this.#compilerVersion,
      nodes,
      compile_diagnostics: diagnostics,
      render_plan: renderPlan,
      provenance,
    };
    return { ok: true, snapshot, diagnostics };
  }

  async fullCompile(document: DesignDocument, useCache = false): Promise<CompileResult> {
    const cacheKey = useCache ? await canvasCompilerCacheKey(this.#compilerVersion, document) : null;
    if (cacheKey) {
      const cached = this.#cache.get(cacheKey);
      if (cached) return { ok: true, snapshot: cached, diagnostics: cached.compile_diagnostics };
    }

    const structure = this.compileStructure(document);
    if (!structure.ok) return structure;
    const diagnostics = [...structure.diagnostics];
    const nodes = new Map<string, CompiledSceneNode>();
    for (const id of structure.snapshot.paint_order) {
      const node = structure.snapshot.nodes.get(id);
      if (!node) continue;
      nodes.set(id, await this.#hydrateNode(document, node, diagnostics));
    }
    const snapshot = await this.#finalize(document, structure.snapshot, nodes, diagnostics);
    if (cacheKey) this.#cache.set(cacheKey, snapshot);
    return { ok: true, snapshot, diagnostics: snapshot.compile_diagnostics };
  }

  async incrementalCompile(
    request: IncrementalCompileRequest,
  ): Promise<CompileResult | IncrementalCompileResult> {
    const diff = request.diff ?? semanticDiff(request.before, request.after);
    const plan = planCompilerDirtyNodes(request.before, request.after, diff);
    const versionMismatch = request.previous.compiler_version !== this.#compilerVersion;
    if (plan.requires_full_compile || versionMismatch) {
      const full = await this.fullCompile(request.after);
      if (!full.ok) return full;
      const diagnostics: CompileDiagnostic[] = [
        ...full.diagnostics,
        {
          code: "INCREMENTAL_FALLBACK",
          severity: "INFO",
          message: versionMismatch
            ? "Compiler version changed; full compile required"
            : `Full compile required: ${plan.reason ?? "structural change"}`,
        },
      ];
      const snapshot = { ...full.snapshot, compile_diagnostics: diagnostics };
      const patch: CompilePatch = {
        compiler_version: this.#compilerVersion,
        document_id: request.after.document_id,
        removed_node_ids: [...plan.removed_node_ids],
        upserted_nodes: snapshot.paint_order
          .map((id) => snapshot.nodes.get(id))
          .filter((node): node is CompiledSceneNode => Boolean(node)),
        paint_order: snapshot.paint_order,
        diagnostics,
      };
      return {
        ok: true,
        snapshot,
        diagnostics,
        patch,
        dirty_node_ids: [...snapshot.paint_order],
        fallback_to_full: true,
      };
    }

    const structure = this.compileStructure(request.after);
    if (!structure.ok) return structure;
    const dirty = new Set(plan.dirty_node_ids);
    const diagnostics = [...structure.diagnostics];
    const nodes = new Map<string, CompiledSceneNode>();

    for (const id of structure.snapshot.paint_order) {
      const structural = structure.snapshot.nodes.get(id);
      if (!structural) continue;
      const previous = request.previous.nodes.get(id);
      if (!previous || dirty.has(id)) {
        nodes.set(id, await this.#hydrateNode(request.after, structural, diagnostics));
        continue;
      }
      const merged: CompiledSceneNode = {
        ...previous,
        id: structural.id,
        kind: structural.kind,
        parent_id: structural.parent_id,
        children: structural.children,
        depth: structural.depth,
        paint_order: structural.paint_order,
        visible: structural.visible,
        locked: structural.locked,
        local_matrix: structural.local_matrix,
        world_matrix: structural.world_matrix,
        local_bounds: structural.local_bounds,
        world_bounds: structural.world_bounds,
        metadata: structural.metadata,
        interaction_flags: structural.interaction_flags,
        placeholder: structural.placeholder,
        resolved_style: structural.resolved_style,
        ...(structural.clip_id ? { clip_id: structural.clip_id } : { clip_id: undefined }),
        ...(structural.mask_id ? { mask_id: structural.mask_id } : { mask_id: undefined }),
      } as CompiledSceneNode;
      nodes.set(id, {
        ...merged,
        render_key: canonicalStringify({
          compiler_version: this.#compilerVersion,
          structural: structural.render_key,
          resolved_style: merged.resolved_style,
          resolved_text: merged.resolved_text
            ? {
                content: merged.resolved_text.content,
                font_ref: merged.resolved_text.font_ref ?? null,
                font: hashableFont(merged.resolved_text.font),
                metrics: merged.resolved_text.metrics ?? null,
              }
            : null,
          resolved_resource: hashableResource(merged.resolved_resource),
        }),
      });
    }

    const snapshot = await this.#finalize(request.after, structure.snapshot, nodes, diagnostics);
    const upserted = snapshot.paint_order
      .map((id) => snapshot.nodes.get(id))
      .filter((node): node is CompiledSceneNode => Boolean(node))
      .filter((node) => !sameNode(request.previous.nodes.get(node.id), node));
    const patch: CompilePatch = {
      compiler_version: this.#compilerVersion,
      document_id: request.after.document_id,
      removed_node_ids: plan.removed_node_ids,
      upserted_nodes: upserted,
      paint_order: snapshot.paint_order,
      diagnostics: snapshot.compile_diagnostics,
    };
    return {
      ok: true,
      snapshot,
      diagnostics: snapshot.compile_diagnostics,
      patch,
      dirty_node_ids: plan.dirty_node_ids,
      fallback_to_full: false,
    };
  }

  async #hydrateNode(
    document: DesignDocument,
    node: CompiledSceneNode,
    diagnostics: CompileDiagnostic[],
  ): Promise<CompiledSceneNode> {
    let resource = node.resolved_resource;
    if (node.asset_id) {
      try {
        const resolved = await this.#assetResolver.resolveAsset(document, node.asset_id, this.#variant);
        if (!resolved) {
          diagnostics.push({
            code: "RESOURCE_MISSING",
            severity: "WARNING",
            message: `Asset ${node.asset_id} could not be resolved`,
            node_id: node.id,
            source: node.asset_id,
          });
          resource = {
            asset_id: node.asset_id,
            variant: this.#variant,
            version: "missing",
            status: "MISSING",
            fingerprint: canonicalStringify({ asset_id: node.asset_id, variant: this.#variant, missing: true }),
          };
        } else {
          resource = resolved;
        }
      } catch (error) {
        diagnostics.push({
          code: "RESOURCE_RESOLUTION_FAILED",
          severity: "WARNING",
          message: error instanceof Error ? error.message : `Asset ${node.asset_id} resolution failed`,
          node_id: node.id,
          source: node.asset_id,
        });
      }
    }

    let resolvedText = node.resolved_text;
    if (resolvedText) {
      let font: ResolvedCompilerFont | null = null;
      if (resolvedText.font_ref) {
        try {
          font = await this.#fontResolver.resolveFont(document, resolvedText.font_ref);
          if (!font) {
            diagnostics.push({
              code: "FONT_MISSING",
              severity: "WARNING",
              message: `Font ${resolvedText.font_ref} could not be resolved`,
              node_id: node.id,
              source: resolvedText.font_ref,
            });
          }
        } catch (error) {
          diagnostics.push({
            code: "FONT_RESOLUTION_FAILED",
            severity: "WARNING",
            message: error instanceof Error ? error.message : `Font ${resolvedText.font_ref} resolution failed`,
            node_id: node.id,
            source: resolvedText.font_ref,
          });
        }
      }
      try {
        const metrics = await this.#textMeasurer.measure(
          resolvedText.content,
          node.resolved_style,
          font,
        );
        resolvedText = {
          ...resolvedText,
          metrics,
          ...(font ? { font } : {}),
        };
      } catch (error) {
        diagnostics.push({
          code: "TEXT_MEASURE_FAILED",
          severity: "WARNING",
          message: error instanceof Error ? error.message : "Text measurement failed",
          node_id: node.id,
        });
      }
    }

    return {
      ...node,
      ...(resource ? { resolved_resource: resource } : {}),
      ...(resolvedText ? { resolved_text: resolvedText } : {}),
      render_key: canonicalStringify({
        compiler_version: this.#compilerVersion,
        structural: node.render_key,
        resolved_style: node.resolved_style,
        resolved_resource: hashableResource(resource),
        resolved_text: resolvedText
          ? {
              content: resolvedText.content,
              font_ref: resolvedText.font_ref ?? null,
              font: hashableFont(resolvedText.font),
              metrics: resolvedText.metrics ?? null,
            }
          : null,
      }),
    };
  }

  async #finalize(
    document: DesignDocument,
    structure: CompiledSceneSnapshot,
    nodes: ReadonlyMap<string, CompiledSceneNode>,
    diagnostics: readonly CompileDiagnostic[],
  ): Promise<CompiledSceneSnapshot> {
    const renderPlan = makeRenderPlan(
      this.#compilerVersion,
      document.document_id,
      structure.paint_order,
      nodes,
    );
    const withoutProvenance = {
      ...structure,
      nodes,
      compile_diagnostics: [...diagnostics],
      render_plan: renderPlan,
    };
    const compileHash = await canonicalSha256(hashablePlan(withoutProvenance));
    const provenance: CanvasCompileProvenance = {
      compiler_version: this.#compilerVersion,
      document_id: document.document_id,
      schema_version: document.schema_version,
      document_version: getDocumentVersion(document),
      resource_versions: resourceVersions(nodes),
      font_versions: fontVersions(nodes),
      compile_hash: compileHash,
    };
    return {
      ...withoutProvenance,
      provenance,
    };
  }
}
