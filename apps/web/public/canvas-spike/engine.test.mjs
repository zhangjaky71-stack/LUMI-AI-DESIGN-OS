import test from "node:test";
import assert from "node:assert/strict";
import {
  CommandHistory,
  MAX_ZOOM,
  MIN_ZOOM,
  cullNodeIds,
  createSeedNodes,
  fitCameraToRect,
  marqueeSelect,
  resizeNode,
  rotateNodeToPointer,
  screenToWorld,
  selectionBounds,
  translateNodes,
  worldToScreen,
  zoomAtScreenPoint,
} from "./engine.mjs";

test("world/screen coordinate round trip is stable", () => {
  const camera = { x: 321.5, y: -84.25, zoom: 1.75 };
  const world = { x: -4096.125, y: 8192.5 };
  const screen = worldToScreen(world, camera);
  const roundTrip = screenToWorld(screen, camera);
  assert.ok(Math.abs(roundTrip.x - world.x) < 1e-9);
  assert.ok(Math.abs(roundTrip.y - world.y) < 1e-9);
});

test("zoom-to-cursor preserves the world anchor and clamps zoom", () => {
  const camera = { x: 20, y: 30, zoom: 1 };
  const anchor = { x: 640, y: 360 };
  const before = screenToWorld(anchor, camera);
  const next = zoomAtScreenPoint(camera, anchor, 2.4);
  const after = screenToWorld(anchor, next);
  assert.deepEqual(after, before);
  assert.equal(zoomAtScreenPoint(camera, anchor, 0).zoom, MIN_ZOOM);
  assert.equal(zoomAtScreenPoint(camera, anchor, 999).zoom, MAX_ZOOM);
});

test("marquee and culling use renderer-independent node bounds", () => {
  const nodes = [
    { id: "a", x: 0, y: 0, width: 100, height: 100 },
    { id: "b", x: 1000, y: 1000, width: 100, height: 100 },
  ];
  assert.deepEqual(marqueeSelect(nodes, { x: -20, y: -20, width: 200, height: 200 }), ["a"]);
  const visible = cullNodeIds(nodes, { x: 0, y: 0, zoom: 1 }, { width: 800, height: 600 }, 0);
  assert.equal(visible.has("a"), true);
  assert.equal(visible.has("b"), false);
});

test("selection transforms do not mutate the persisted spike nodes", () => {
  const original = [
    { id: "a", x: 10, y: 20, width: 120, height: 80, rotation: 0 },
    { id: "b", x: 200, y: 220, width: 80, height: 80, rotation: 0 },
  ];
  const translated = translateNodes(original, ["a"], { x: 30, y: -10 });
  assert.equal(original[0].x, 10);
  assert.equal(translated[0].x, 40);
  const resized = resizeNode(translated[0], "se", { x: 25, y: 15 });
  assert.equal(resized.width, 145);
  assert.equal(resized.height, 95);
  const rotated = rotateNodeToPointer(resized, { x: resized.x + resized.width / 2, y: resized.y - 100 });
  assert.ok(Number.isFinite(rotated.rotation));
});

test("selection bounds and fit-camera support large scenes", () => {
  const nodes = createSeedNodes(2000);
  const ids = nodes.slice(0, 500).map((node) => node.id);
  const bounds = selectionBounds(nodes, ids);
  assert.ok(bounds && bounds.width > 0 && bounds.height > 0);
  const camera = fitCameraToRect(bounds, { width: 1440, height: 900 }, 64);
  assert.ok(camera.zoom >= MIN_ZOOM && camera.zoom <= MAX_ZOOM);
});

test("undo/redo command stack restores applied mutations", () => {
  let value = 1;
  const history = new CommandHistory(10);
  history.execute({ apply: () => { value = 2; }, revert: () => { value = 1; } });
  assert.equal(value, 2);
  assert.equal(history.canUndo, true);
  assert.equal(history.undo(), true);
  assert.equal(value, 1);
  assert.equal(history.canRedo, true);
  assert.equal(history.redo(), true);
  assert.equal(value, 2);
});
