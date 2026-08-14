import type { CameraState, CanvasViewport, Point, Rect } from "./types";

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

export function viewportWorldRect(camera: CameraState, viewport: CanvasViewport): Rect {
  return {
    x: camera.x,
    y: camera.y,
    width: viewport.width / camera.zoom,
    height: viewport.height / camera.zoom,
  };
}

export function fitWorldRect(
  rect: Rect,
  viewport: CanvasViewport,
  paddingScreenPx = 48,
): CameraState {
  const usableWidth = Math.max(1, viewport.width - paddingScreenPx * 2);
  const usableHeight = Math.max(1, viewport.height - paddingScreenPx * 2);
  const width = Math.max(1e-6, rect.width);
  const height = Math.max(1e-6, rect.height);
  const zoom = clampZoom(Math.min(usableWidth / width, usableHeight / height));
  const worldViewportWidth = viewport.width / zoom;
  const worldViewportHeight = viewport.height / zoom;
  return {
    x: rect.x + rect.width / 2 - worldViewportWidth / 2,
    y: rect.y + rect.height / 2 - worldViewportHeight / 2,
    zoom,
  };
}

export function zoomFromWheelDelta(camera: CameraState, deltaY: number, sensitivity = 0.0015): number {
  if (!Number.isFinite(deltaY)) return camera.zoom;
  return clampZoom(camera.zoom * Math.exp(-deltaY * sensitivity));
}

export function physicalCanvasSize(viewport: CanvasViewport, devicePixelRatio: number): CanvasViewport {
  const dpr = Number.isFinite(devicePixelRatio) ? Math.max(1, devicePixelRatio) : 1;
  return {
    width: Math.max(1, Math.round(viewport.width * dpr)),
    height: Math.max(1, Math.round(viewport.height * dpr)),
  };
}
