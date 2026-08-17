import { MAX_ZOOM, MIN_ZOOM, type CameraState, type Point, type Rect, type Viewport } from "./types";

function finite(value: number, fallback: number): number { return Number.isFinite(value) ? value : fallback; }
export function clampZoom(zoom: number): number { return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, finite(zoom, 1))); }

export class CanvasCamera {
  private stateValue: CameraState;
  private viewportValue: Viewport;
  constructor(state: CameraState = { x: 0, y: 0, zoom: 1 }, viewport: Viewport = { width: 1, height: 1, dpr: 1 }) {
    this.stateValue = { x: finite(state.x, 0), y: finite(state.y, 0), zoom: clampZoom(state.zoom) };
    this.viewportValue = normalizeViewport(viewport);
  }
  get state(): CameraState { return this.stateValue; }
  get viewport(): Viewport { return this.viewportValue; }
  setViewport(viewport: Viewport): void { this.viewportValue = normalizeViewport(viewport); }
  setState(next: CameraState): void { this.stateValue = { x: finite(next.x, 0), y: finite(next.y, 0), zoom: clampZoom(next.zoom) }; }
  worldToScreen(point: Point): Point {
    return { x: (point.x - this.stateValue.x) * this.stateValue.zoom, y: (point.y - this.stateValue.y) * this.stateValue.zoom };
  }
  screenToWorld(point: Point): Point {
    return { x: point.x / this.stateValue.zoom + this.stateValue.x, y: point.y / this.stateValue.zoom + this.stateValue.y };
  }
  panByScreen(dx: number, dy: number): CameraState {
    this.stateValue = { ...this.stateValue, x: this.stateValue.x - dx / this.stateValue.zoom, y: this.stateValue.y - dy / this.stateValue.zoom };
    return this.stateValue;
  }
  zoomToCursor(screen: Point, nextZoom: number): CameraState {
    const anchor = this.screenToWorld(screen);
    const zoom = clampZoom(nextZoom);
    this.stateValue = { x: anchor.x - screen.x / zoom, y: anchor.y - screen.y / zoom, zoom };
    return this.stateValue;
  }
  fitBounds(bounds: Rect, padding = 32): CameraState {
    if (!(bounds.width > 0) || !(bounds.height > 0)) return this.stateValue;
    const usableWidth = Math.max(1, this.viewportValue.width - padding * 2);
    const usableHeight = Math.max(1, this.viewportValue.height - padding * 2);
    const zoom = clampZoom(Math.min(usableWidth / bounds.width, usableHeight / bounds.height));
    const visibleWorldWidth = this.viewportValue.width / zoom;
    const visibleWorldHeight = this.viewportValue.height / zoom;
    this.stateValue = {
      x: bounds.x + bounds.width / 2 - visibleWorldWidth / 2,
      y: bounds.y + bounds.height / 2 - visibleWorldHeight / 2,
      zoom,
    };
    return this.stateValue;
  }
  worldViewportRect(overscanPx = 0): Rect {
    const amount = Math.max(0, overscanPx) / this.stateValue.zoom;
    return {
      x: this.stateValue.x - amount,
      y: this.stateValue.y - amount,
      width: this.viewportValue.width / this.stateValue.zoom + amount * 2,
      height: this.viewportValue.height / this.stateValue.zoom + amount * 2,
    };
  }
}

export function normalizeViewport(viewport: Viewport): Viewport {
  return {
    width: Math.max(1, finite(viewport.width, 1)),
    height: Math.max(1, finite(viewport.height, 1)),
    dpr: Math.max(0.5, Math.min(8, finite(viewport.dpr, 1))),
  };
}
