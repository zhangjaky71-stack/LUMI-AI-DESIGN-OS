import { describe, expect, it } from "vitest";

import { fitWorldRect, physicalCanvasSize, screenToWorld, worldToScreen } from "./camera";
import { projectDesignDocument } from "./ir-scene";
import { snapRect } from "./snapping";
import type { DesignDocument } from "../../design-ir/src/index";

function documentFixture(): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "snap-doc",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame", "target"] },
      frame: {
        id: "frame",
        kind: "FRAME",
        parent_id: "root",
        children: [],
        transform: { x: 100, y: 100, width: 400, height: 300 },
      },
      target: {
        id: "target",
        kind: "SHAPE",
        parent_id: "root",
        children: [],
        transform: { x: 520, y: 100, width: 100, height: 100 },
      },
    },
    resources: {},
    metadata: { document_version: 1 },
  };
}

describe("Canvas camera", () => {
  it("fits world bounds and preserves world/screen round trips", () => {
    const camera = fitWorldRect({ x: 100, y: 50, width: 800, height: 600 }, { width: 1440, height: 900 }, 50);
    const world = { x: 333.5, y: 444.25 };
    const restored = screenToWorld(worldToScreen(world, camera), camera);
    expect(restored.x).toBeCloseTo(world.x, 8);
    expect(restored.y).toBeCloseTo(world.y, 8);
  });

  it("uses DPR only for physical renderer size, not world coordinates", () => {
    expect(physicalCanvasSize({ width: 750, height: 500 }, 2)).toEqual({ width: 1500, height: 1000 });
  });
});

describe("Canvas snapping", () => {
  it("snaps near a frame edge using screen-space tolerance", () => {
    const scene = projectDesignDocument(documentFixture());
    const result = snapRect(
      { x: 495, y: 150, width: 50, height: 50 },
      scene,
      new Set(["target"]),
      { zoom: 1, tolerance_screen_px: 6 },
    );
    expect(result.rect.x).toBe(500);
    expect(result.guides.some((guide) => guide.axis === "x")).toBe(true);
  });

  it("can fall back to a configured grid", () => {
    const scene = projectDesignDocument(documentFixture());
    const result = snapRect(
      { x: 23, y: 41, width: 20, height: 20 },
      scene,
      new Set(["target"]),
      { zoom: 1, tolerance_screen_px: 4, grid_size: 8, include_grid: true },
    );
    expect(result.rect.x).toBe(24);
    expect(result.rect.y).toBe(40);
    expect(result.guides.some((guide) => guide.kind === "grid")).toBe(true);
  });
});
