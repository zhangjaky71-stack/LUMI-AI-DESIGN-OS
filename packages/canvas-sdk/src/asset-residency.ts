import type { CanvasSceneSnapshot } from "./ir-scene";
import { CanvasResourceManager, type AssetTier } from "./resource-manager";

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

function key(assetId: string, tier: AssetTier): string {
  return `${assetId}:${tier}`;
}

export class CanvasAssetResidency<T> implements CanvasAssetResidencyPort {
  readonly #manager: CanvasResourceManager<T>;
  readonly #desiredByNode = new Map<string, DesiredAsset>();
  readonly #loaded = new Map<string, T>();
  #generation = 0;
  #invalidate: (() => void) | null = null;

  constructor(manager: CanvasResourceManager<T>) {
    this.#manager = manager;
  }

  setInvalidator(invalidate: () => void): void {
    this.#invalidate = invalidate;
  }

  update(scene: CanvasSceneSnapshot, visibleIds: ReadonlySet<string>, zoom: number): void {
    this.#generation += 1;
    const generation = this.#generation;
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
      this.#manager.release(current.assetId, current.tier);
      this.#desiredByNode.delete(nodeId);
    }

    for (const [nodeId, wanted] of next) {
      const current = this.#desiredByNode.get(nodeId);
      if (current && current.assetId === wanted.assetId && current.tier === wanted.tier) continue;
      this.#desiredByNode.set(nodeId, wanted);
      void this.#manager.acquire(wanted.assetId, wanted.tier).then((resource) => {
        const stillWanted = this.#desiredByNode.get(nodeId);
        if (
          generation > this.#generation ||
          !stillWanted ||
          stillWanted.assetId !== wanted.assetId ||
          stillWanted.tier !== wanted.tier
        ) {
          this.#manager.release(wanted.assetId, wanted.tier);
          return;
        }
        this.#loaded.set(key(wanted.assetId, wanted.tier), resource);
        this.#invalidate?.();
      });
    }
  }

  textureForAsset(assetId: string): T | null {
    return (
      this.#loaded.get(key(assetId, "full")) ??
      this.#loaded.get(key(assetId, "preview")) ??
      this.#loaded.get(key(assetId, "thumbnail")) ??
      null
    );
  }

  destroy(): void {
    for (const desired of this.#desiredByNode.values()) {
      this.#manager.release(desired.assetId, desired.tier);
    }
    this.#desiredByNode.clear();
    this.#loaded.clear();
    this.#manager.destroy();
    this.#invalidate = null;
  }
}
