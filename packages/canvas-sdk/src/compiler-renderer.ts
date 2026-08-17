import type {
  CompiledRendererPatchBindings,
  CompiledSceneBridge,
  CompiledSceneNode,
  CompiledScenePatch,
  CompiledSceneSnapshot,
  CompileDiagnostic,
} from "./compiler-types";
import type { CanvasDiagnostic, RenderNodeSnapshot, SceneSnapshot } from "./types";

function rotationDegrees(node: CompiledSceneNode): number {
  return (Math.atan2(node.worldTransform.b, node.worldTransform.a) * 180) / Math.PI;
}

export function compiledNodeToRenderNode(node: CompiledSceneNode): RenderNodeSnapshot {
  return {
    id: node.id,
    kind: node.kind,
    sourceKind: node.sourceKind,
    parentId: node.parentId,
    childIds: node.childIds,
    bounds: node.worldBounds,
    rotationDeg: rotationDegrees(node),
    visible: node.visible,
    locked: node.locked,
    opacity: node.opacity,
    zOrder: node.zOrder,
    ...(node.resolvedResource ? { assetId: node.resolvedResource.assetId } : {}),
    ...(node.resolvedText ? { text: node.resolvedText.content } : {}),
    styleRefs: Object.keys(node.styleVersions).sort(),
    diagnosticCodes: node.diagnosticCodes,
  };
}

export function compileDiagnosticsToCanvas(
  diagnostics: readonly CompileDiagnostic[],
): readonly CanvasDiagnostic[] {
  return diagnostics.map((item) => ({
    code: item.code,
    message: item.message,
    severity: item.severity,
    ...(item.nodeId ? { nodeId: item.nodeId } : {}),
  }));
}

export function compiledSceneToCanvasScene(snapshot: CompiledSceneSnapshot): SceneSnapshot {
  const nodes = new Map<string, RenderNodeSnapshot>();
  for (const id of snapshot.orderedIds) nodes.set(id, compiledNodeToRenderNode(snapshot.nodes.get(id)!));
  return {
    documentId: snapshot.documentId,
    nodes,
    orderedIds: snapshot.orderedIds,
    diagnostics: compileDiagnosticsToCanvas(snapshot.diagnostics),
  };
}

export class DefaultCompiledSceneBridge implements CompiledSceneBridge {
  toCanvasScene(snapshot: CompiledSceneSnapshot): SceneSnapshot { return compiledSceneToCanvasScene(snapshot); }
  toCanvasDiagnostics(diagnostics: readonly CompileDiagnostic[]): readonly CanvasDiagnostic[] {
    return compileDiagnosticsToCanvas(diagnostics);
  }
}

export function applyCompiledPatch(
  bindings: CompiledRendererPatchBindings,
  patch: CompiledScenePatch,
): void {
  for (const id of patch.removedNodeIds) bindings.removeNode(id);
  for (const node of patch.upsertedNodes) bindings.upsertNode(compiledNodeToRenderNode(node));
  bindings.setPaintOrder(patch.orderedIds);
}
