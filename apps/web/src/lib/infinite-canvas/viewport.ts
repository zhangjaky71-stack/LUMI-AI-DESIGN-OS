import type { CanvasSceneNode, CameraState, CanvasViewport, Rect } from "@lumi/canvas-sdk";
import { viewportWorldRect } from "@lumi/canvas-sdk";

export function intersects(left: Rect, right: Rect, padding = 0): boolean {
  return !(
    left.x + left.width < right.x - padding ||
    right.x + right.width < left.x - padding ||
    left.y + left.height < right.y - padding ||
    right.y + right.height < left.y - padding
  );
}

export function cullSceneNodes(
  nodes: readonly CanvasSceneNode[],
  camera: CameraState,
  viewport: CanvasViewport,
  selectedIds: ReadonlySet<string>,
): CanvasSceneNode[] {
  const world = viewportWorldRect(camera, viewport);
  const padding = 180 / Math.max(camera.zoom, 0.05);
  const lowZoom = camera.zoom < 0.18;
  return nodes.filter((node) => {
    if (!node.visible || node.kind === "DOCUMENT_ROOT" || node.kind === "GUIDE") return false;
    if (selectedIds.has(node.id)) return true;
    if (!intersects(node.world_bounds, world, padding)) return false;
    if (lowZoom && !["FRAME", "IMAGE", "SHAPE"].includes(node.kind)) return false;
    return true;
  });
}
