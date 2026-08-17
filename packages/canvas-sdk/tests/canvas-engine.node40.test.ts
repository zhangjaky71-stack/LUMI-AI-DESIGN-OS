import { describe, expect, it } from "vitest";
import type { ConstraintPreflight, DesignDocument } from "../../design-ir/src/index";
import {
  CanvasCamera,
  CanvasCommandHistory,
  CanvasController,
  CanvasOperationGateway,
  CanvasResourceManager,
  HeadlessRendererAdapter,
  SelectionModel,
  SpatialIndex,
  TextEditSession,
  TransformSession,
  buildScene,
  createFragment,
  graphemes,
  keyboardCommand,
  remapFragmentAssets,
  runStructuralBenchmark,
  sanitizePastedText,
  snapRect,
} from "../src/index";

function document(): DesignDocument {
  return {
    schema_version: "lumi.design-ir/1.0",
    document_id: "doc-node40",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame", "shape-a", "shape-b", "text", "image"] },
      frame: { id: "frame", kind: "FRAME", parent_id: "root", children: [], transform: { x: 0, y: 0, width: 750, height: 1000 } },
      "shape-a": { id: "shape-a", kind: "SHAPE", parent_id: "root", children: [], transform: { x: 10, y: 20, width: 100, height: 50 } },
      "shape-b": { id: "shape-b", kind: "SHAPE", parent_id: "root", children: [], transform: { x: 200, y: 20, width: 100, height: 50 }, locked: true },
      text: { id: "text", kind: "TEXT", parent_id: "root", children: [], transform: { x: 10, y: 100, width: 220, height: 60 }, content: "中文🙂" },
      image: { id: "image", kind: "IMAGE", parent_id: "root", children: [], transform: { x: 300, y: 120, width: 120, height: 120 }, asset_id: "asset-1" },
    },
    resources: {},
    metadata: { document_version: 0, applied_operation_ids: [] },
  };
}

describe("NODE-40 Canvas Engine V1", () => {
  it("round-trips world/screen coordinates and preserves zoom-to-cursor anchor", () => {
    const camera = new CanvasCamera({ x: 10, y: 20, zoom: 2 }, { width: 1200, height: 800, dpr: 2 });
    const world = { x: 123.25, y: 456.5 };
    const screen = camera.worldToScreen(world);
    expect(camera.screenToWorld(screen)).toEqual(world);
    const cursor = { x: 333, y: 222 };
    const anchor = camera.screenToWorld(cursor);
    camera.zoomToCursor(cursor, 4);
    expect(camera.screenToWorld(cursor)).toEqual(anchor);
    expect(camera.viewport.dpr).toBe(2);
  });

  it("builds a renderer-neutral scene and isolates malformed nodes", () => {
    const value = document();
    const malformed: DesignDocument = {
      ...value,
      nodes: {
        ...value.nodes,
        broken: { id: "broken", kind: "custom:plugin", parent_id: "root", children: [], transform: { x: 0, y: 0, width: -1, height: 10 } },
        root: { ...value.nodes.root!, children: [...value.nodes.root!.children, "broken"] },
      },
    };
    const scene = buildScene(malformed);
    expect(scene.nodes.get("broken")?.kind).toBe("PLACEHOLDER");
    expect(scene.diagnostics.map((item) => item.code)).toContain("CANVAS_NODE_GEOMETRY_INVALID");
    expect(JSON.stringify(malformed)).not.toContain("Pixi");
  });

  it("supports hit testing, shift multi-select, marquee and locked transform filtering", () => {
    const scene = buildScene(document());
    const index = new SpatialIndex();
    index.rebuild(scene);
    const selection = new SelectionModel();
    expect(selection.click(scene, index, { x: 20, y: 30 })).toBe("shape-a");
    selection.marquee(scene, { x: 0, y: 0, width: 350, height: 90 }, { shift: true });
    expect(selection.ids.has("shape-b")).toBe(true);
    expect(selection.transformable(scene)).toContain("shape-a");
    expect(selection.transformable(scene)).not.toContain("shape-b");
  });

  it("supports select-through layer cycling", () => {
    const value = document();
    const overlap: DesignDocument = {
      ...value,
      nodes: {
        ...value.nodes,
        top: { id: "top", kind: "SHAPE", parent_id: "root", children: [], transform: { x: 10, y: 20, width: 100, height: 50 } },
        root: { ...value.nodes.root!, children: [...value.nodes.root!.children, "top"] },
      },
    };
    const scene = buildScene(overlap); const index = new SpatialIndex(); index.rebuild(scene); const selection = new SelectionModel();
    expect(selection.click(scene, index, { x: 20, y: 30 }, { cycle: 0 })).toBe("top");
    expect(selection.click(scene, index, { x: 20, y: 30 }, { cycle: 1 })).toBe("shape-a");
  });

  it("snaps to nearby/grid anchors in world coordinates", () => {
    const scene = buildScene(document());
    const result = snapRect({ x: 96, y: 20, width: 50, height: 50 }, [scene.nodes.get("shape-b")!], { zoom: 1, gridSize: 10 });
    expect(result.rect.x).toBe(95);
    expect(result.guides.length).toBeGreaterThan(0);
  });

  it("commits local transform preview through Design IR and rolls back on constraint denial", () => {
    const preflight: ConstraintPreflight = (_document, operation) => operation.type === "MOVE_NODE" && Number(operation.payload.x) > 500
      ? [{ code: "IR_CONSTRAINT_FAILED", message: "outside safe area", node_ids: ["shape-a"], operation_id: operation.operation_id }]
      : [];
    const gateway = new CanvasOperationGateway(document(), preflight);
    let session = new TransformSession("move", ["shape-a"], buildScene(gateway.document), gateway);
    session.update({ dx: 100, dy: 10 });
    expect(session.commit().ok).toBe(true);
    expect(gateway.document.nodes["shape-a"]?.transform?.x).toBe(110);
    session = new TransformSession("move", ["shape-a"], buildScene(gateway.document), gateway);
    session.update({ dx: 500, dy: 0 });
    const denied = session.commit();
    expect(denied.ok).toBe(false);
    expect(gateway.document.nodes["shape-a"]?.transform?.x).toBe(110);
    expect(session.preview.bounds.get("shape-a")?.x).toBe(110);
  });

  it("never starts transforms for locked nodes", () => {
    const gateway = new CanvasOperationGateway(document());
    expect(() => new TransformSession("move", ["shape-b"], buildScene(gateway.document), gateway)).toThrow("CANVAS_TRANSFORM_TARGET_LOCKED");
  });

  it("keeps UI command history separate and revalidates undo/redo operations", () => {
    const gateway = new CanvasOperationGateway(document());
    const history = new CanvasCommandHistory();
    const forward = [{ type: "MOVE_NODE" as const, targetIds: ["shape-a"], payload: { x: 30, y: 40 } }];
    const inverse = [{ type: "MOVE_NODE" as const, targetIds: ["shape-a"], payload: { x: 10, y: 20 } }];
    expect(gateway.commitBatch(forward).ok).toBe(true);
    history.push({ label: "move", forward, inverse, coalesceKey: "drag:shape-a" });
    expect(history.undo(gateway)?.ok).toBe(true);
    expect(gateway.document.nodes["shape-a"]?.transform?.x).toBe(10);
    expect(history.redo(gateway)?.ok).toBe(true);
    expect(gateway.document.nodes["shape-a"]?.transform?.x).toBe(30);
  });

  it("does not commit text while Chinese IME composition is active and preserves graphemes", () => {
    const session = new TextEditSession("text", "中");
    session.compositionStart(); session.input("中文");
    expect(() => session.commit()).toThrow("CANVAS_TEXT_COMPOSITION_ACTIVE");
    session.compositionEnd("中文🙂");
    expect(session.commit().payload.content).toBe("中文🙂");
    expect(graphemes("👨‍👩‍👧‍👦")).toHaveLength(1);
    expect(sanitizePastedText("<b>你好</b><script>x()</script>", "plain")).toBe("你好");
  });

  it("uses authorized asset resolution and destroys zero-ref LRU textures", async () => {
    let destroyed = 0;
    const manager = new CanvasResourceManager(
      { resolve: async (assetId, tier) => ({ assetId, tier, url: `https://assets.example/${assetId}/${tier}` }) },
      { load: async (source) => ({ key: source.url, destroy: () => { destroyed += 1; } }) },
      1,
    );
    await manager.acquire("asset-a"); manager.release("asset-a"); await manager.acquire("asset-b");
    expect(destroyed).toBe(1);
    manager.destroy();
    expect(destroyed).toBeGreaterThanOrEqual(2);
  });

  it("remaps cross-project asset ids through policy instead of trusting copied URLs", async () => {
    const fragment = createFragment(document(), ["image"], "project-a");
    const mapped = await remapFragmentAssets(fragment, "project-b", { remapAsset: async (assetId) => `copy-${assetId}` });
    expect(mapped.nodes.image?.asset_id).toBe("copy-asset-1");
    expect(mapped.sourceProjectId).toBe("project-b");
  });

  it("does not hijack shortcuts inside text inputs", () => {
    expect(keyboardCommand({ key: "z", ctrlKey: true, target: { tagName: "TEXTAREA" } })).toBeNull();
    expect(keyboardCommand({ key: "z", ctrlKey: true })).toBe("undo");
    expect(keyboardCommand({ key: "z", ctrlKey: true, shiftKey: true })).toBe("redo");
    expect(keyboardCommand({ key: "ArrowRight" })).toBe("nudge-right");
  });

  it("culls the scene to the camera viewport and retains high-DPI viewport state", async () => {
    const renderer = new HeadlessRendererAdapter();
    const controller = new CanvasController(document(), renderer, { viewport: { width: 100, height: 80, dpr: 2 } });
    await controller.mount();
    expect(renderer.lastFrame?.viewport.dpr).toBe(2);
    expect(renderer.lastFrame!.visibleNodes.length).toBeLessThan(controller.scene.nodes.size);
    controller.pan(-1000, 0);
    expect(renderer.lastFrame).not.toBeNull();
    controller.destroy();
  });

  it("runs deterministic 2k/10k structural culling benchmarks without claiming browser FPS", () => {
    const normal = runStructuralBenchmark(2_000);
    const stress = runStructuralBenchmark(10_000);
    expect(normal.nodeCount).toBe(2_000);
    expect(stress.nodeCount).toBe(10_000);
    expect(normal.visibleCount).toBeLessThan(normal.nodeCount);
    expect(stress.visibleCount).toBeLessThan(stress.nodeCount);
    expect(stress.buildMs).toBeGreaterThanOrEqual(0);
  });
});
