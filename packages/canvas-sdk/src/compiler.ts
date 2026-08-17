import {
  canonicalStringify,
  computeSemanticDiff,
  hashDocument,
  validateDocument,
  type DesignDocument,
  type DesignNode,
  type JsonValue,
  type SemanticDiff,
} from "../../design-ir/src/index";
import { computeDirtyNodeIds, resourceInvalidationDirtyIds } from "./compiler-dirty";
import { fingerprintCompiledNode, hashCompiledScene, hashNodeSource } from "./compiler-hash";
import { IDENTITY_MATRIX, localBounds, localMatrix, multiplyMatrix, transformedBounds } from "./compiler-math";
import {
  DeterministicTextMeasurer,
  DocumentStyleResolver,
  MissingAssetResolver,
  MissingFontResolver,
} from "./compiler-resolvers";
import {
  CANVAS_COMPILER_VERSION,
  type ArtifactCompilerProvenanceSink,
  type CanvasCompilerOptions,
  type CanvasCompilerProvenance,
  type CompileDiagnostic,
  type CompileResult,
  type CompiledSceneNode,
  type CompiledScenePatch,
  type CompiledSceneSnapshot,
  type IncrementalCompileRequest,
  type IncrementalCompileResult,
  type Matrix2D,
  type ResourceInvalidation,
  type ResolvedCompilerAsset,
  type ResolvedCompilerFont,
  type ResolvedCompilerStyle,
} from "./compiler-types";
import { CANVAS_RENDER_KINDS, type CanvasRenderKind, type Rect } from "./types";

const SUPPORTED = new Set<string>(CANVAS_RENDER_KINDS);

interface StructureState {
  readonly orderedIds: readonly string[];
  readonly world: ReadonlyMap<string, Matrix2D>;
  readonly local: ReadonlyMap<string, Matrix2D>;
  readonly bounds: ReadonlyMap<string, Rect | null>;
  readonly z: ReadonlyMap<string, number>;
}

function stringProp(node: DesignNode, key: string): string | undefined {
  const value = node[key];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function inlineStyle(node: DesignNode): Readonly<Record<string, JsonValue>> {
  const value = node.style;
  if (value === null || typeof value !== "object" || Array.isArray(value)) return {};
  const output: Record<string, JsonValue> = {};
  for (const key of Object.keys(value as Record<string, unknown>).sort()) {
    const child = (value as Record<string, unknown>)[key];
    if (
      child === null || typeof child === "string" || typeof child === "number" ||
      typeof child === "boolean" || Array.isArray(child) || typeof child === "object"
    ) output[key] = child as JsonValue;
  }
  return output;
}

function opacity(node: DesignNode): number {
  const value = typeof node.opacity === "number" && Number.isFinite(node.opacity) ? node.opacity : 1;
  return Math.max(0, Math.min(1, value));
}

function structure(document: DesignDocument): StructureState {
  const orderedIds: string[] = [];
  const world = new Map<string, Matrix2D>();
  const local = new Map<string, Matrix2D>();
  const bounds = new Map<string, Rect | null>();
  const z = new Map<string, number>();
  let index = 0;
  const walk = (id: string, parentWorld: Matrix2D): void => {
    const node = document.nodes[id]!;
    const localValue = node.kind === "DOCUMENT_ROOT" ? IDENTITY_MATRIX : localMatrix(node);
    const worldValue = multiplyMatrix(parentWorld, localValue);
    local.set(id, localValue);
    world.set(id, worldValue);
    bounds.set(id, node.kind === "DOCUMENT_ROOT" ? { x: 0, y: 0, width: 0, height: 0 } : localBounds(node));
    if (node.kind !== "DOCUMENT_ROOT") {
      z.set(id, index++);
      orderedIds.push(id);
    }
    for (const childId of node.children) walk(childId, worldValue);
  };
  walk(document.root_id, IDENTITY_MATRIX);
  return { orderedIds, world, local, bounds, z };
}

function interaction(node: DesignNode, kind: string) {
  const locked = node.locked === true;
  return {
    selectable: node.visible !== false && kind !== "GUIDE",
    transformable: !locked && !["GUIDE", "MASK"].includes(kind),
    hitTestable: node.visible !== false && kind !== "GUIDE",
    editable: !locked && kind === "TEXT",
  };
}

function diagnostic(
  code: CompileDiagnostic["code"],
  message: string,
  severity: CompileDiagnostic["severity"],
  nodeId?: string,
  resourceId?: string,
): CompileDiagnostic {
  return {
    code, message, severity,
    ...(nodeId ? { nodeId } : {}),
    ...(resourceId ? { resourceId } : {}),
  };
}

function changedResourceRefs(before: DesignDocument, after: DesignDocument): readonly string[] {
  const refs = new Set([...Object.keys(before.resources), ...Object.keys(after.resources)]);
  return [...refs].filter(
    (ref) => canonicalStringify(before.resources[ref] ?? null) !== canonicalStringify(after.resources[ref] ?? null),
  ).sort();
}

function addResourceDependents(document: DesignDocument, refs: readonly string[], dirty: Set<string>): void {
  if (!refs.length) return;
  const changed = new Set(refs);
  for (const [id, node] of Object.entries(document.nodes)) {
    if ((node.style_refs ?? []).some((ref) => changed.has(ref))) dirty.add(id);
    const fontRef = stringProp(node, "font_asset_id") ?? stringProp(node, "font_ref");
    if (fontRef && changed.has(fontRef)) dirty.add(id);
    const assetId = stringProp(node, "asset_id");
    if (assetId && changed.has(assetId)) dirty.add(id);
  }
}

function makePlaceholder(
  node: DesignNode,
  state: StructureState,
  diagnosticCodes: readonly CompileDiagnostic["code"][],
  sourceFingerprint: string,
): CompiledSceneNode {
  const local = state.local.get(node.id) ?? IDENTITY_MATRIX;
  const world = state.world.get(node.id) ?? IDENTITY_MATRIX;
  const localBox = state.bounds.get(node.id) ?? null;
  const box = localBox ?? { x: 0, y: 0, width: 40, height: 40 };
  return {
    id: node.id,
    kind: "PLACEHOLDER",
    sourceKind: node.kind,
    parentId: node.parent_id,
    childIds: [...node.children],
    localTransform: local,
    worldTransform: world,
    localBounds: box,
    worldBounds: transformedBounds(world, box),
    resolvedStyle: {},
    styleVersions: {},
    zOrder: state.z.get(node.id) ?? 0,
    interactionFlags: interaction(node, node.kind),
    visible: node.visible !== false,
    locked: node.locked === true,
    opacity: opacity(node),
    placeholder: true,
    diagnosticCodes,
    sourceFingerprint,
    renderFingerprint: "",
  };
}

function withRenderFingerprint(node: CompiledSceneNode): CompiledSceneNode {
  return { ...node, renderFingerprint: fingerprintCompiledNode(node) };
}

export class CanvasCompiler {
  readonly compilerVersion: string;
  private readonly tier;
  private readonly assetResolver;
  private readonly fontResolver;
  private readonly styleResolver;
  private readonly textMeasurer;

  constructor(options: CanvasCompilerOptions = {}) {
    this.compilerVersion = options.compilerVersion ?? CANVAS_COMPILER_VERSION;
    this.tier = options.resourceTier ?? "preview";
    this.assetResolver = options.assetResolver ?? new MissingAssetResolver();
    this.fontResolver = options.fontResolver ?? new MissingFontResolver();
    this.styleResolver = options.styleResolver ?? new DocumentStyleResolver();
    this.textMeasurer = options.textMeasurer ?? new DeterministicTextMeasurer();
  }

  async compileFull(document: DesignDocument): Promise<CompileResult> {
    const structural = validateDocument(document);
    if (structural.length) {
      return {
        ok: false,
        diagnostics: structural.map((issue) => diagnostic(
          "COMPILER_STRUCTURAL_INVALID",
          `${issue.code}: ${issue.message}`,
          "error",
          issue.node_ids?.[0],
        )),
      };
    }
    const state = structure(document);
    const compiled = new Map<string, CompiledSceneNode>();
    const diagnostics: CompileDiagnostic[] = [];
    for (const id of state.orderedIds) {
      const result = await this.compileNode(document, document.nodes[id]!, state);
      compiled.set(id, result.node);
      diagnostics.push(...result.diagnostics);
    }
    const snapshot = await this.finalize(document, state.orderedIds, compiled, diagnostics);
    return { ok: true, snapshot, diagnostics: snapshot.diagnostics };
  }

  async compileIncremental(request: IncrementalCompileRequest): Promise<IncrementalCompileResult> {
    const structural = validateDocument(request.after);
    if (structural.length) {
      return {
        ok: false,
        diagnostics: structural.map((issue) => diagnostic(
          "COMPILER_STRUCTURAL_INVALID",
          `${issue.code}: ${issue.message}`,
          "error",
          issue.node_ids?.[0],
        )),
      };
    }
    const versionMismatch = request.previous.compilerVersion !== this.compilerVersion;
    const stalePrevious = request.previous.documentId !== request.before.document_id;
    if (versionMismatch || stalePrevious) {
      const full = await this.compileFull(request.after);
      if (!full.ok) return full;
      const fallbackDiagnostic = diagnostic(
        versionMismatch ? "COMPILER_VERSION_MISMATCH" : "COMPILER_INCREMENTAL_FALLBACK",
        versionMismatch
          ? `Previous compiler ${request.previous.compilerVersion} does not match ${this.compilerVersion}.`
          : "Previous compiled scene belongs to a different document identity.",
        "warning",
      );
      const snapshot = { ...full.snapshot, diagnostics: [...full.snapshot.diagnostics, fallbackDiagnostic] };
      return {
        ok: true,
        snapshot,
        diagnostics: snapshot.diagnostics,
        dirtyNodeIds: [...snapshot.orderedIds],
        fallbackToFull: true,
        patch: {
          compilerVersion: this.compilerVersion,
          documentId: snapshot.documentId,
          removedNodeIds: request.previous.orderedIds.filter((id) => !snapshot.nodes.has(id)),
          upsertedNodes: snapshot.orderedIds.map((id) => snapshot.nodes.get(id)!),
          orderedIds: snapshot.orderedIds,
          diagnostics: snapshot.diagnostics,
          sceneHash: snapshot.sceneHash,
        },
      };
    }

    const diff = request.diff ?? computeSemanticDiff(request.before, request.after);
    const dirty = new Set(computeDirtyNodeIds(request.before, request.after, diff));
    addResourceDependents(request.after, changedResourceRefs(request.before, request.after), dirty);
    return this.compileDirty(request.previous, request.after, [...dirty].sort(), false);
  }

  async compileResourceInvalidation(
    previous: CompiledSceneSnapshot,
    document: DesignDocument,
    invalidation: ResourceInvalidation,
  ): Promise<IncrementalCompileResult> {
    const dirty = resourceInvalidationDirtyIds(document, previous, invalidation);
    return this.compileDirty(previous, document, dirty, false);
  }

  async recordProvenance(
    snapshot: CompiledSceneSnapshot,
    sink: ArtifactCompilerProvenanceSink,
  ): Promise<void> {
    await sink.recordCompilerProvenance(snapshot.provenance);
  }

  private async compileDirty(
    previous: CompiledSceneSnapshot,
    document: DesignDocument,
    dirtyIds: readonly string[],
    fallbackToFull: boolean,
  ): Promise<IncrementalCompileResult> {
    const structural = validateDocument(document);
    if (structural.length) {
      return {
        ok: false,
        diagnostics: structural.map((issue) => diagnostic(
          "COMPILER_STRUCTURAL_INVALID",
          `${issue.code}: ${issue.message}`,
          "error",
          issue.node_ids?.[0],
        )),
      };
    }
    const state = structure(document);
    const dirty = new Set(dirtyIds);
    const compiled = new Map<string, CompiledSceneNode>();
    const diagnostics: CompileDiagnostic[] = previous.diagnostics.filter((item) =>
      (!item.nodeId || (!dirty.has(item.nodeId) && Boolean(document.nodes[item.nodeId]))),
    );
    const upserted = new Map<string, CompiledSceneNode>();

    for (const id of state.orderedIds) {
      const old = previous.nodes.get(id);
      if (dirty.has(id) || !old) {
        const result = await this.compileNode(document, document.nodes[id]!, state);
        compiled.set(id, result.node);
        upserted.set(id, result.node);
        diagnostics.push(...result.diagnostics);
        continue;
      }
      const nextZ = state.z.get(id) ?? old.zOrder;
      const next = nextZ === old.zOrder ? old : { ...old, zOrder: nextZ };
      compiled.set(id, next);
      if (next !== old) upserted.set(id, next);
    }

    const removedNodeIds = previous.orderedIds.filter((id) => !compiled.has(id));
    const snapshot = await this.finalize(document, state.orderedIds, compiled, diagnostics);
    return {
      ok: true,
      snapshot,
      diagnostics: snapshot.diagnostics,
      dirtyNodeIds: [...dirty].sort(),
      fallbackToFull,
      patch: {
        compilerVersion: this.compilerVersion,
        documentId: document.document_id,
        removedNodeIds,
        upsertedNodes: [...upserted.values()].sort((a, b) => a.zOrder - b.zOrder || a.id.localeCompare(b.id)),
        orderedIds: snapshot.orderedIds,
        diagnostics: snapshot.diagnostics,
        sceneHash: snapshot.sceneHash,
      },
    };
  }

  private async compileNode(
    document: DesignDocument,
    node: DesignNode,
    state: StructureState,
  ): Promise<{ node: CompiledSceneNode; diagnostics: readonly CompileDiagnostic[] }> {
    const diagnostics: CompileDiagnostic[] = [];
    const diagnosticCodes: CompileDiagnostic["code"][] = [];
    const sourceFingerprint = await hashNodeSource({
      node,
      parentWorld: node.parent_id ? state.world.get(node.parent_id) ?? IDENTITY_MATRIX : IDENTITY_MATRIX,
      compilerVersion: this.compilerVersion,
    });
    try {
      const box = state.bounds.get(node.id) ?? null;
      if (!box || !SUPPORTED.has(node.kind)) {
        const message = !box
          ? `Node ${node.id} has invalid geometry.`
          : `Node ${node.id} uses unsupported render kind ${node.kind}.`;
        const item = diagnostic("COMPILER_NODE_PLACEHOLDER", message, "warning", node.id);
        diagnostics.push(item);
        diagnosticCodes.push(item.code);
        return { node: withRenderFingerprint(makePlaceholder(node, state, diagnosticCodes, sourceFingerprint)), diagnostics };
      }

      const styleResolution = this.styleResolver.resolveStyle(document, node.style_refs ?? []);
      const resolvedStyle: Record<string, JsonValue> = { ...styleResolution.style, ...inlineStyle(node) };
      for (const ref of styleResolution.missingRefs) {
        const item = diagnostic(
          "COMPILER_STYLE_TOKEN_MISSING",
          `Style/token ${ref} could not be resolved for node ${node.id}.`,
          "warning",
          node.id,
          ref,
        );
        diagnostics.push(item);
        diagnosticCodes.push(item.code);
      }

      const maskId = stringProp(node, "mask_id");
      const clipId = stringProp(node, "clip_id");
      for (const ref of [maskId, clipId]) {
        if (ref && !document.nodes[ref]) {
          const item = diagnostic(
            "COMPILER_MASK_REFERENCE_MISSING",
            `Mask/clip reference ${ref} is missing for node ${node.id}.`,
            "warning",
            node.id,
            ref,
          );
          diagnostics.push(item);
          diagnosticCodes.push(item.code);
        }
      }

      let resolvedResource: ResolvedCompilerAsset | undefined;
      const assetId = stringProp(node, "asset_id");
      if (node.kind === "IMAGE" || node.kind === "VIDEO") {
        if (!assetId) {
          const item = diagnostic(
            "COMPILER_RESOURCE_MISSING",
            `${node.kind} node ${node.id} has no asset_id.`,
            "warning",
            node.id,
          );
          diagnostics.push(item);
          diagnosticCodes.push(item.code);
        } else {
          try {
            const resource = await this.assetResolver.resolveAsset({ document, assetId, tier: this.tier, nodeId: node.id });
            if (!resource || resource.status !== "ready") {
              const item = diagnostic(
                "COMPILER_RESOURCE_MISSING",
                `Asset ${assetId} is unavailable for node ${node.id}.`,
                "warning",
                node.id,
                assetId,
              );
              diagnostics.push(item);
              diagnosticCodes.push(item.code);
            } else if (resource.assetId !== assetId || resource.tier !== this.tier) {
              throw new Error("resolver identity/tier mismatch");
            } else resolvedResource = resource;
          } catch (error) {
            const item = diagnostic(
              "COMPILER_RESOURCE_RESOLUTION_FAILED",
              `Asset ${assetId} resolution failed: ${error instanceof Error ? error.message : "unknown"}.`,
              "warning",
              node.id,
              assetId,
            );
            diagnostics.push(item);
            diagnosticCodes.push(item.code);
          }
        }
      }

      let resolvedText: CompiledSceneNode["resolvedText"];
      if (node.kind === "TEXT") {
        const content = typeof node.content === "string" ? node.content.normalize("NFC") : "";
        const fontRef = stringProp(node, "font_asset_id") ?? stringProp(node, "font_ref");
        let font: ResolvedCompilerFont | null = null;
        if (fontRef) {
          try {
            font = await this.fontResolver.resolveFont({ document, fontRef, nodeId: node.id });
            if (!font || font.status !== "ready") {
              const item = diagnostic(
                "COMPILER_FONT_MISSING",
                `Font ${fontRef} is unavailable for node ${node.id}.`,
                "warning",
                node.id,
                fontRef,
              );
              diagnostics.push(item);
              diagnosticCodes.push(item.code);
              font = null;
            }
          } catch (error) {
            const item = diagnostic(
              "COMPILER_FONT_RESOLUTION_FAILED",
              `Font ${fontRef} resolution failed: ${error instanceof Error ? error.message : "unknown"}.`,
              "warning",
              node.id,
              fontRef,
            );
            diagnostics.push(item);
            diagnosticCodes.push(item.code);
          }
        }
        try {
          const metrics = await this.textMeasurer.measure({ content, style: resolvedStyle, font, nodeId: node.id });
          if (![metrics.width, metrics.height, metrics.baseline].every(Number.isFinite)) throw new Error("non-finite metrics");
          resolvedText = {
            content,
            ...(fontRef ? { fontRef } : {}),
            ...(font ? { font } : {}),
            metrics,
          };
        } catch (error) {
          const item = diagnostic(
            "COMPILER_TEXT_MEASURE_FAILED",
            `Text measurement failed for node ${node.id}: ${error instanceof Error ? error.message : "unknown"}.`,
            "warning",
            node.id,
          );
          diagnostics.push(item);
          diagnosticCodes.push(item.code);
          resolvedText = { content, ...(fontRef ? { fontRef } : {}), metrics: { width: box.width, height: box.height, baseline: 0 } };
        }
      }

      const local = state.local.get(node.id) ?? IDENTITY_MATRIX;
      const world = state.world.get(node.id) ?? IDENTITY_MATRIX;
      const placeholder = diagnosticCodes.some((code) =>
        code === "COMPILER_RESOURCE_MISSING" || code === "COMPILER_RESOURCE_RESOLUTION_FAILED");
      const kind = node.kind as CanvasRenderKind;
      return {
        node: withRenderFingerprint({
          id: node.id,
          kind: placeholder ? "PLACEHOLDER" : kind,
          sourceKind: node.kind,
          parentId: node.parent_id,
          childIds: [...node.children],
          localTransform: local,
          worldTransform: world,
          localBounds: box,
          worldBounds: transformedBounds(world, box),
          ...(clipId && document.nodes[clipId] ? { clipId } : {}),
          ...(maskId && document.nodes[maskId] ? { maskId } : {}),
          resolvedStyle,
          styleVersions: styleResolution.versions,
          ...(resolvedText ? { resolvedText } : {}),
          ...(resolvedResource ? { resolvedResource } : {}),
          zOrder: state.z.get(node.id) ?? 0,
          interactionFlags: interaction(node, node.kind),
          visible: node.visible !== false,
          locked: node.locked === true,
          opacity: opacity(node),
          placeholder,
          diagnosticCodes,
          sourceFingerprint,
          renderFingerprint: "",
        }),
        diagnostics,
      };
    } catch (error) {
      const item = diagnostic(
        "COMPILER_NODE_PLACEHOLDER",
        `Node ${node.id} compile failed in isolation: ${error instanceof Error ? error.message : "unknown"}.`,
        "warning",
        node.id,
      );
      return {
        node: withRenderFingerprint(makePlaceholder(node, state, [item.code], sourceFingerprint)),
        diagnostics: [item],
      };
    }
  }

  private async finalize(
    document: DesignDocument,
    orderedIds: readonly string[],
    nodes: ReadonlyMap<string, CompiledSceneNode>,
    diagnostics: readonly CompileDiagnostic[],
  ): Promise<CompiledSceneSnapshot> {
    const sceneHash = await hashCompiledScene(this.compilerVersion, document.document_id, orderedIds, nodes);
    const documentHash = await hashDocument(document);
    const resourceVersions: Record<string, string> = {};
    const fontVersions: Record<string, string> = {};
    const tokenVersions: Record<string, string> = {};
    for (const id of orderedIds) {
      const node = nodes.get(id)!;
      if (node.resolvedResource) resourceVersions[node.resolvedResource.assetId] = node.resolvedResource.resourceVersion;
      if (node.resolvedText?.font) fontVersions[node.resolvedText.font.fontRef] = node.resolvedText.font.resourceVersion;
      for (const [ref, version] of Object.entries(node.styleVersions)) tokenVersions[ref] = version;
    }
    const provenance: CanvasCompilerProvenance = {
      compiler_version: this.compilerVersion,
      document_id: document.document_id,
      schema_version: document.schema_version,
      document_hash: documentHash,
      scene_hash: sceneHash,
      resource_versions: Object.fromEntries(Object.entries(resourceVersions).sort()),
      font_versions: Object.fromEntries(Object.entries(fontVersions).sort()),
      token_versions: Object.fromEntries(Object.entries(tokenVersions).sort()),
    };
    return {
      compilerVersion: this.compilerVersion,
      documentId: document.document_id,
      nodes,
      orderedIds,
      diagnostics: [...diagnostics].sort((a, b) =>
        `${a.nodeId ?? ""}\0${a.code}\0${a.resourceId ?? ""}`.localeCompare(`${b.nodeId ?? ""}\0${b.code}\0${b.resourceId ?? ""}`)),
      sceneHash,
      provenance,
    };
  }
}
