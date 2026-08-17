import type { DesignDocument, SemanticDiff } from "../../design-ir/src/index";
import { CanvasCompiler } from "./compiler";
import { applyCompiledPatch, compiledNodeToRenderNode } from "./compiler-renderer";
import type {
  CompiledRendererPatchBindings,
  CompiledSceneSnapshot,
  IncrementalCompileResult,
  ResourceInvalidation,
} from "./compiler-types";

export class CanvasCompilerRendererRuntime {
  private documentValue: DesignDocument | null = null;
  private snapshotValue: CompiledSceneSnapshot | null = null;

  constructor(
    readonly compiler: CanvasCompiler,
    private readonly bindings: CompiledRendererPatchBindings,
  ) {}

  get document(): DesignDocument | null { return this.documentValue; }
  get snapshot(): CompiledSceneSnapshot | null { return this.snapshotValue; }

  async open(document: DesignDocument): Promise<CompiledSceneSnapshot> {
    const result = await this.compiler.compileFull(document);
    if (!result.ok) throw new Error(`CANVAS_COMPILER_OPEN_FAILED: ${result.diagnostics[0]?.message ?? "unknown"}`);
    for (const id of result.snapshot.orderedIds) {
      this.bindings.upsertNode(compiledNodeToRenderNode(result.snapshot.nodes.get(id)!));
    }
    this.bindings.setPaintOrder(result.snapshot.orderedIds);
    this.documentValue = document;
    this.snapshotValue = result.snapshot;
    return result.snapshot;
  }

  async update(document: DesignDocument, diff?: SemanticDiff): Promise<IncrementalCompileResult> {
    if (!this.documentValue || !this.snapshotValue) {
      const snapshot = await this.open(document);
      return {
        ok: true,
        snapshot,
        diagnostics: snapshot.diagnostics,
        dirtyNodeIds: snapshot.orderedIds,
        fallbackToFull: true,
        patch: {
          compilerVersion: snapshot.compilerVersion,
          documentId: snapshot.documentId,
          removedNodeIds: [],
          upsertedNodes: snapshot.orderedIds.map((id) => snapshot.nodes.get(id)!),
          orderedIds: snapshot.orderedIds,
          diagnostics: snapshot.diagnostics,
          sceneHash: snapshot.sceneHash,
        },
      };
    }
    const result = await this.compiler.compileIncremental({
      previous: this.snapshotValue,
      before: this.documentValue,
      after: document,
      ...(diff ? { diff } : {}),
    });
    if (result.ok) {
      applyCompiledPatch(this.bindings, result.patch);
      this.documentValue = document;
      this.snapshotValue = result.snapshot;
    }
    return result;
  }

  async invalidateResources(invalidation: ResourceInvalidation): Promise<IncrementalCompileResult> {
    if (!this.documentValue || !this.snapshotValue) throw new Error("CANVAS_COMPILER_RUNTIME_NOT_OPEN");
    const result = await this.compiler.compileResourceInvalidation(this.snapshotValue, this.documentValue, invalidation);
    if (result.ok) {
      applyCompiledPatch(this.bindings, result.patch);
      this.snapshotValue = result.snapshot;
    }
    return result;
  }
}
