export interface Point {
  readonly x: number;
  readonly y: number;
}

export interface Size {
  readonly width: number;
  readonly height: number;
}

export interface Rect extends Point, Size {}

export interface CameraState {
  readonly x: number;
  readonly y: number;
  readonly zoom: number;
}

export type SpikeNodeKind = "frame" | "rect" | "text" | "image";

export interface SpikeNode {
  readonly id: string;
  readonly kind: SpikeNodeKind;
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
  readonly rotation: number;
  readonly zIndex: number;
  readonly text?: string;
  readonly assetRef?: string;
  readonly fill?: number;
}

export interface MutableSpikeNode {
  id: string;
  kind: SpikeNodeKind;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  zIndex: number;
  text?: string;
  assetRef?: string;
  fill?: number;
}

export interface CanvasViewport {
  readonly width: number;
  readonly height: number;
}

export interface TransformPatch {
  readonly x?: number;
  readonly y?: number;
  readonly width?: number;
  readonly height?: number;
  readonly rotation?: number;
  readonly zIndex?: number;
}
