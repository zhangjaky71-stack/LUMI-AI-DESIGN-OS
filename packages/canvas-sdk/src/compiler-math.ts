import type { DesignNode } from "../../design-ir/src/index";
import type { Matrix2D } from "./compiler-types";
import type { Rect } from "./types";

export const IDENTITY_MATRIX: Matrix2D = { a: 1, b: 0, c: 0, d: 1, tx: 0, ty: 0 };

function finite(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function multiplyMatrix(left: Matrix2D, right: Matrix2D): Matrix2D {
  return {
    a: left.a * right.a + left.c * right.b,
    b: left.b * right.a + left.d * right.b,
    c: left.a * right.c + left.c * right.d,
    d: left.b * right.c + left.d * right.d,
    tx: left.a * right.tx + left.c * right.ty + left.tx,
    ty: left.b * right.tx + left.d * right.ty + left.ty,
  };
}

export function localMatrix(node: DesignNode): Matrix2D {
  const transform = node.transform ?? {};
  const rotation = (finite(transform.rotation_deg, 0) * Math.PI) / 180;
  const cos = Math.cos(rotation);
  const sin = Math.sin(rotation);
  const sx = finite(transform.scale_x, 1);
  const sy = finite(transform.scale_y, 1);
  return {
    a: cos * sx,
    b: sin * sx,
    c: -sin * sy,
    d: cos * sy,
    tx: finite(transform.x, finite(node.bounds?.x, 0)),
    ty: finite(transform.y, finite(node.bounds?.y, 0)),
  };
}

export function localBounds(node: DesignNode): Rect | null {
  const width = finite(node.transform?.width, finite(node.bounds?.width, 0));
  const height = finite(node.transform?.height, finite(node.bounds?.height, 0));
  if (width < 0 || height < 0 || !Number.isFinite(width) || !Number.isFinite(height)) return null;
  return { x: 0, y: 0, width, height };
}

function point(matrix: Matrix2D, x: number, y: number): readonly [number, number] {
  return [matrix.a * x + matrix.c * y + matrix.tx, matrix.b * x + matrix.d * y + matrix.ty];
}

export function transformedBounds(matrix: Matrix2D, bounds: Rect): Rect {
  const values = [
    point(matrix, bounds.x, bounds.y),
    point(matrix, bounds.x + bounds.width, bounds.y),
    point(matrix, bounds.x, bounds.y + bounds.height),
    point(matrix, bounds.x + bounds.width, bounds.y + bounds.height),
  ];
  const xs = values.map(([x]) => x);
  const ys = values.map(([, y]) => y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}
