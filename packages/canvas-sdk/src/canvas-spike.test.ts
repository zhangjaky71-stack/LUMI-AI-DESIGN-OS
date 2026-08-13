import { describe, expect, it } from "vitest";

import { runCullingBenchmark } from "./benchmark";
import { screenToWorld, worldToScreen, zoomAtScreenPoint } from "./camera";
import { nodesInRect, unionBounds } from "./geometry";
import { CommandStack } from "./history";
import { SpikeSceneStore, createSpikeSeedScene } from "./scene";


describe("canvas spike coordinate model", () => {
  it("round-trips world and screen coordinates", () => {
    const camera = { x: -320, y: 180, zoom: 1.75 };
    const world = { x: 842.5, y: -91.25 };
    const screen = worldToScreen(world, camera);
    const restored = screenToWorld(screen, camera);
    expect(restored.x).toBeCloseTo(world.x, 8);
    expect(restored.y).toBeCloseTo(world.y, 8);
  });

  it("keeps the zoom anchor fixed in world space", () => {
    const camera = { x: 100, y: 50, zoom: 1 };
    const anchor = { x: 640, y: 360 };
    const before = screenToWorld(anchor, camera);
    const zoomed = zoomAtScreenPoint(camera, anchor, 2.25);
    const after = screenToWorld(anchor, zoomed);
    expect(after.x).toBeCloseTo(before.x, 8);
    expect(after.y).toBeCloseTo(before.y, 8);
  });
});


describe("canvas spike scene operations", () => {
  it("marquee-selects intersecting nodes and computes union bounds", () => {
    const scene = createSpikeSeedScene();
    const selected = nodesInRect(scene, { x: 100, y: 100, width: 600, height: 300 });
    expect(selected).toContain("rect-accent");
    expect(selected).toContain("text-title");
    const bounds = unionBounds(scene.filter((node) => selected.includes(node.id)));
    expect(bounds).not.toBeNull();
    expect(bounds?.width).toBeGreaterThan(400);
  });

  it("duplicates nodes without mutating the source identity", () => {
    const store = new SpikeSceneStore(createSpikeSeedScene());
    const source = store.get("image-product");
    const [copy] = store.duplicate(["image-product"]);
    expect(copy?.id).toBe("image-product-copy-1");
    expect(copy?.assetRef).toBe(source?.assetRef);
    expect(copy?.x).toBe((source?.x ?? 0) + 24);
    expect(store.get("image-product")?.id).toBe("image-product");
  });

  it("supports undo and redo without tying state to a renderer", () => {
    const store = new SpikeSceneStore(createSpikeSeedScene());
    const history = new CommandStack();
    const before = store.list();
    const after = before.map((node) =>
      node.id === "rect-accent" ? { ...node, x: node.x + 40, y: node.y + 12 } : node,
    );
    history.execute({
      label: "move",
      do: () => store.replaceAll(after),
      undo: () => store.replaceAll(before),
    });
    expect(store.get("rect-accent")?.x).toBe(180);
    expect(history.undo()).toBe(true);
    expect(store.get("rect-accent")?.x).toBe(140);
    expect(history.redo()).toBe(true);
    expect(store.get("rect-accent")?.x).toBe(180);
  });
});


describe("canvas spike culling fixture", () => {
  it("exercises ten thousand nodes deterministically", () => {
    let clock = 0;
    const result = runCullingBenchmark(10_000, 10, () => {
      clock += 0.5;
      return clock;
    });
    expect(result.nodeCount).toBe(10_000);
    expect(result.iterations).toBe(10);
    expect(result.visibleMean).toBeGreaterThan(0);
    expect(result.operationsPerSecond).toBeGreaterThan(0);
  });
});
