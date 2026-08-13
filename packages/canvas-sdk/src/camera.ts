import type { CameraState, Point } from "./types";

export const MIN_ZOOM = 0.05;
export const MAX_ZOOM = 8;

export function clampZoom(zoom: number): number {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
}

export function worldToScreen(point: Point, camera: CameraState): Point {
  return {
    x: (point.x - camera.x) * camera.zoom,
    y: (point.y - camera.y) * camera.zoom,
  };
}

export function screenToWorld(point: Point, camera: CameraState): Point {
  return {
    x: point.x / camera.zoom + camera.x,
    y: point.y / camera.zoom + camera.y,
  };
}

export function panCamera(camera: CameraState, screenDelta: Point): CameraState {
  return {
    ...camera,
    x: camera.x - screenDelta.x / camera.zoom,
    y: camera.y - screenDelta.y / camera.zoom,
  };
}

export function zoomAtScreenPoint(
  camera: CameraState,
  screenAnchor: Point,
  nextZoom: number,
): CameraState {
  const worldAnchor = screenToWorld(screenAnchor, camera);
  const zoom = clampZoom(nextZoom);

  return {
    x: worldAnchor.x - screenAnchor.x / zoom,
    y: worldAnchor.y - screenAnchor.y / zoom,
    zoom,
  };
}
