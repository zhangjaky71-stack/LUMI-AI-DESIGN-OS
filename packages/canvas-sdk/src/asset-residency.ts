import type { AssetTier } from "./asset-cache";
import type { CanvasSceneSnapshot } from "./ir-scene";
import { CanvasResourceManager } from "./resource-manager";

export interface CanvasAssetResidencyPort {
  update(scene: CanvasSceneSnapshot, visibleIds: ReadonlySet<string>, zoom: number): void;
  setInvalidator?(invalidate: () => void): void;
  destroy(): void;
}

interface DesiredAsset {
  readonly assetId: string;
  readonly tier: AssetTier;
}

function tierForZoom(zoom: number): AssetTier {
  const value = Math.abs(zoom);
  if (value < 0.35) return "thumbnail";
  if (value < 1.5) return "preview";
  return "full";
}

export class CanvasAssetResidency<T> implements CanvasAssetResidencyPort {
  readonly #manager: CanvasResourceManager<T>;
  readonly #desiredByNode = new Map<string, DesiredAsset>();
  readonly #requestTokenByNode = new Map<string, number>();
  #nextRequestToken = 0;
  #invalidate: (() => void) | null = null;

  constructor(manager: CanvasResourceManager<T>) {
    this.#manager = manager;
  }

  setInvalidator(invalidate: () => void): void {
    this.#invalidate = invalidate;
  }

  update(scene: CanvasSceneSnapshot, visibleIds: ReadonlySet<string>, zoom: number): void {
    const next = new Map<string, DesiredAsset>();
    const tier = tierForZoom(zoom);

    for (const id of visibleIds) {
      const node = scene.nodes.get(id);
      if (!node?.asset_id || !node.visible) continue;
      next.set(id, { assetId: node.asset_id, tier });
    }

    for (const [nodeId, current] of this.#desiredByNode) {
      const wanted = next.get(nodeId);
      if (wanted && wanted.assetId === current.assetId && wanted.tier === current.tier) continue;
      this.#requestTokenByNode.delete(nodeId);
      this.#manager.release(current.assetId, current.tier);
      this.#desiredByNode.delete(nodeId);
    }

    for (const [nodeId, wanted] of next) {
      const current = this.#desiredByNode.get(nodeId);
      if (current && current.assetId === wanted.assetId && current.tier === wanted.tier) continue;
      this.#desiredByNode.set(nodeId, wanted);
      this.#nextRequestToken += 1;
      const requestToken = this.#nextRequestToken;
      this.#requestTokenByNode.set(nodeId, requestToken);
      void this.#manager.acquire(wanted.assetId, wanted.tier).then(() => {
        const stillWanted = this.#desiredByNode.get(nodeId);
        const stillCurrent = this.#requestTokenByNode.get(nodeId) === requestToken;
        if (
          !stillCurrent ||
          !stillWanted ||
          stillWanted.assetId !== wanted.assetId ||
          stillWanted.tier !== wanted.tier
        ) {
          this.#manager.release(wanted.assetId, wanted.tier);
          return;
        }
        this.#invalidate?.();
      });
    }
  }

  textureForAsset(assetId: string): T | null {
    return (
      this.#manager.peek(assetId, "full") ??
      this.#manager.peek(assetId, "preview") ??
      this.#manager.peek(assetId, "thumbnail") ??
      null
    );
  }

  destroy(): void {
    for (const desired of this.#desiredByNode.values()) {
      this.#manager.release(desired.assetId, desired.tier);
    }
    this.#desiredByNode.clear();
    this.#requestTokenByNode.clear();
    this.#manager.destroy();
    this.#invalidate = null;
  }
}
