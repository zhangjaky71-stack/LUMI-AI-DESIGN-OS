import { canonicalStringify } from "../../design-ir/src/index";
import type { CompiledSceneNode } from "./compiler-types";

async function sha256(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalStringify(value));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function deterministicNode(node: CompiledSceneNode): unknown {
  return {
    id: node.id,
    kind: node.kind,
    sourceKind: node.sourceKind,
    parentId: node.parentId,
    childIds: node.childIds,
    localTransform: node.localTransform,
    worldTransform: node.worldTransform,
    localBounds: node.localBounds,
    worldBounds: node.worldBounds,
    clipId: node.clipId ?? null,
    maskId: node.maskId ?? null,
    resolvedStyle: node.resolvedStyle,
    styleVersions: node.styleVersions,
    resolvedText: node.resolvedText ? {
      content: node.resolvedText.content,
      fontRef: node.resolvedText.fontRef ?? null,
      font: node.resolvedText.font ? {
        fontRef: node.resolvedText.font.fontRef,
        family: node.resolvedText.font.family,
        style: node.resolvedText.font.style,
        weight: node.resolvedText.font.weight,
        resourceVersion: node.resolvedText.font.resourceVersion,
        fingerprint: node.resolvedText.font.fingerprint,
        status: node.resolvedText.font.status,
      } : null,
      metrics: node.resolvedText.metrics,
    } : null,
    resolvedResource: node.resolvedResource ? {
      assetId: node.resolvedResource.assetId,
      kind: node.resolvedResource.kind,
      tier: node.resolvedResource.tier,
      resourceVersion: node.resolvedResource.resourceVersion,
      fingerprint: node.resolvedResource.fingerprint,
      status: node.resolvedResource.status,
      mimeType: node.resolvedResource.mimeType ?? null,
      width: node.resolvedResource.width ?? null,
      height: node.resolvedResource.height ?? null,
    } : null,
    zOrder: node.zOrder,
    interactionFlags: node.interactionFlags,
    visible: node.visible,
    locked: node.locked,
    opacity: node.opacity,
    placeholder: node.placeholder,
    diagnosticCodes: node.diagnosticCodes,
    sourceFingerprint: node.sourceFingerprint,
  };
}

function fnv1a32(text: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return `fnv1a32:${hash.toString(16).padStart(8, "0")}`;
}

export function fingerprintCompiledNode(node: CompiledSceneNode): string {
  return fnv1a32(canonicalStringify(deterministicNode(node)));
}

export async function hashCompiledScene(
  compilerVersion: string,
  documentId: string,
  orderedIds: readonly string[],
  nodes: ReadonlyMap<string, CompiledSceneNode>,
): Promise<string> {
  return sha256({
    compilerVersion,
    documentId,
    orderedIds,
    fingerprints: orderedIds.map((id) => nodes.get(id)!.renderFingerprint),
  });
}

export async function hashNodeSource(value: unknown): Promise<string> {
  return fnv1a32(canonicalStringify(value));
}
