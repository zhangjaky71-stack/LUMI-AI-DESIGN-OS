import type { DesignTransform } from "../../design-ir/src/index";
import type { Point, Rect } from "./types";

export interface Matrix2D {
  readonly a: number;
  readonly b: number;
  readonly c: number;
  readonly d: number;
  readonly tx: number;
  readonly ty: number;
}

export const IDENTITY_MATRIX: Matrix2D = { a: 1, b: 0, c: 0, d: 1, tx: 0, ty: 0 };

export function multiplyMatrix(parent: Matrix2D, local: Matrix2D): Matrix2D {
  return {
    a: parent.a * local.a + parent.c * local.b,
    b: parent.b * local.a + parent.d * local.b,
    c: parent.a * local.c + parent.c * local.d,
    d: parent.b * local.c + parent.d * local.d,
    tx: parent.a * local.tx + parent.c * local.ty + parent.tx,
    ty: parent.b * local.tx + parent.d * local.ty + parent.ty,
  };
}

export function invertMatrix(matrix: Matrix2D): Matrix2D | null {
  const determinant = matrix.a * matrix.d - matrix.b * matrix.c;
  if (!Number.isFinite(determinant) || Math.abs(determinant) < 1e-12) return null;
  return {
    a: matrix.d / determinant,
    b: -matrix.b / determinant,
    c: -matrix.c / determinant,
    d: matrix.a / determinant,
    tx: (matrix.c * matrix.ty - matrix.d * matrix.tx) / determinant,
    ty: (matrix.b * matrix.tx - matrix.a * matrix.ty) / determinant,
  };
}

export function applyMatrix(matrix: Matrix2D, point: Point): Point {
  return {
    x: matrix.a * point.x + matrix.c * point.y + matrix.tx,
    y: matrix.b * point.x + matrix.d * point.y + matrix.ty,
  };
}

function finite(value: number | undefined, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function transformToMatrix(transform: DesignTransform = {}): Matrix2D {
  const x = finite(transform.x, 0);
  const y = finite(transform.y, 0);
  const width = finite(transform.width, 0);
  const height = finite(transform.height, 0);
  const scaleX = finite(transform.scale_x, 1);
  const scaleY = finite(transform.scale_y, 1);
  const rotation = (finite(transform.rotation_deg, 0) * Math.PI) / 180;
  const skewX = (finite(transform.skew_x, 0) * Math.PI) / 180;
  const skewY = (finite(transform.skew_y, 0) * Math.PI) / 180;
  const anchorX = finite(transform.anchor_x, 0) * width;
  const anchorY = finite(transform.anchor_y, 0) * height;

  const cosine = Math.cos(rotation);
  const sine = Math.sin(rotation);
  const a = cosine * scaleX - Math.sin(skewY) * sine * scaleY;
  const b = sine * scaleX + Math.sin(skewY) * cosine * scaleY;
  const c = Math.sin(skewX) * cosine * scaleX - sine * scaleY;
  const d = Math.sin(skewX) * sine * scaleX + cosine * scaleY;

  return {
    a,
    b,
    c,
    d,
    tx: x + anchorX - a * anchorX - c * anchorY,
    ty: y + anchorY - b * anchorX - d * anchorY,
  };
}

export function transformedRectBounds(matrix: Matrix2D, width: number, height: number): Rect {
  const corners = [
    applyMatrix(matrix, { x: 0, y: 0 }),
    applyMatrix(matrix, { x: width, y: 0 }),
    applyMatrix(matrix, { x: width, y: height }),
    applyMatrix(matrix, { x: 0, y: height }),
  ];
  const xs = corners.map((point) => point.x);
  const ys = corners.map((point) => point.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

export function matrixApproximatelyEqual(left: Matrix2D, right: Matrix2D, epsilon = 1e-8): boolean {
  return (
    Math.abs(left.a - right.a) <= epsilon &&
    Math.abs(left.b - right.b) <= epsilon &&
    Math.abs(left.c - right.c) <= epsilon &&
    Math.abs(left.d - right.d) <= epsilon &&
    Math.abs(left.tx - right.tx) <= epsilon &&
    Math.abs(left.ty - right.ty) <= epsilon
  );
}
