export const MIN_ZOOM = 0.05;
export const MAX_ZOOM = 8;
export const MIN_NODE_SIZE = 16;

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export function worldToScreen(point, camera) {
  return {
    x: point.x * camera.zoom + camera.x,
    y: point.y * camera.zoom + camera.y,
  };
}

export function screenToWorld(point, camera) {
  return {
    x: (point.x - camera.x) / camera.zoom,
    y: (point.y - camera.y) / camera.zoom,
  };
}

export function zoomAtScreenPoint(camera, anchor, requestedZoom) {
  const zoom = clamp(requestedZoom, MIN_ZOOM, MAX_ZOOM);
  const worldAnchor = screenToWorld(anchor, camera);
  return {
    x: anchor.x - worldAnchor.x * zoom,
    y: anchor.y - worldAnchor.y * zoom,
    zoom,
  };
}

export function visibleWorldRect(camera, viewport, padding = 0) {
  const topLeft = screenToWorld({ x: -padding, y: -padding }, camera);
  const bottomRight = screenToWorld(
    { x: viewport.width + padding, y: viewport.height + padding },
    camera,
  );
  return {
    x: topLeft.x,
    y: topLeft.y,
    width: bottomRight.x - topLeft.x,
    height: bottomRight.y - topLeft.y,
  };
}

export function normalizeRect(rect) {
  const x = rect.width >= 0 ? rect.x : rect.x + rect.width;
  const y = rect.height >= 0 ? rect.y : rect.y + rect.height;
  return {
    x,
    y,
    width: Math.abs(rect.width),
    height: Math.abs(rect.height),
  };
}

export function intersects(a, b) {
  const aa = normalizeRect(a);
  const bb = normalizeRect(b);
  return !(
    aa.x + aa.width < bb.x ||
    bb.x + bb.width < aa.x ||
    aa.y + aa.height < bb.y ||
    bb.y + bb.height < aa.y
  );
}

export function nodeBounds(node) {
  return {
    x: node.x,
    y: node.y,
    width: node.width,
    height: node.height,
  };
}

export function selectionBounds(nodes, selectedIds) {
  const selected = nodes.filter((node) => selectedIds.includes(node.id));
  if (selected.length === 0) return null;

  const minX = Math.min(...selected.map((node) => node.x));
  const minY = Math.min(...selected.map((node) => node.y));
  const maxX = Math.max(...selected.map((node) => node.x + node.width));
  const maxY = Math.max(...selected.map((node) => node.y + node.height));
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

export function marqueeSelect(nodes, worldRect) {
  const normalized = normalizeRect(worldRect);
  return nodes
    .filter((node) => intersects(nodeBounds(node), normalized))
    .map((node) => node.id);
}

export function cullNodeIds(nodes, camera, viewport, padding = 160) {
  const visible = visibleWorldRect(camera, viewport, padding);
  const result = new Set();
  for (const node of nodes) {
    if (intersects(nodeBounds(node), visible)) result.add(node.id);
  }
  return result;
}

export function translateNodes(nodes, selectedIds, delta) {
  const selected = new Set(selectedIds);
  return nodes.map((node) =>
    selected.has(node.id)
      ? { ...node, x: node.x + delta.x, y: node.y + delta.y }
      : node,
  );
}

export function resizeNode(node, handle, delta) {
  let x = node.x;
  let y = node.y;
  let width = node.width;
  let height = node.height;

  if (handle.includes("e")) width = Math.max(MIN_NODE_SIZE, node.width + delta.x);
  if (handle.includes("s")) height = Math.max(MIN_NODE_SIZE, node.height + delta.y);

  if (handle.includes("w")) {
    const next = Math.max(MIN_NODE_SIZE, node.width - delta.x);
    x = node.x + (node.width - next);
    width = next;
  }
  if (handle.includes("n")) {
    const next = Math.max(MIN_NODE_SIZE, node.height - delta.y);
    y = node.y + (node.height - next);
    height = next;
  }

  return { ...node, x, y, width, height };
}

export function rotateNodeToPointer(node, pointerWorld) {
  const cx = node.x + node.width / 2;
  const cy = node.y + node.height / 2;
  const radians = Math.atan2(pointerWorld.y - cy, pointerWorld.x - cx) + Math.PI / 2;
  return { ...node, rotation: radians };
}

export function fitCameraToRect(rect, viewport, padding = 80) {
  const normalized = normalizeRect(rect);
  const safeWidth = Math.max(1, normalized.width);
  const safeHeight = Math.max(1, normalized.height);
  const zoom = clamp(
    Math.min(
      Math.max(1, viewport.width - padding * 2) / safeWidth,
      Math.max(1, viewport.height - padding * 2) / safeHeight,
    ),
    MIN_ZOOM,
    MAX_ZOOM,
  );
  const centerX = normalized.x + normalized.width / 2;
  const centerY = normalized.y + normalized.height / 2;
  return {
    zoom,
    x: viewport.width / 2 - centerX * zoom,
    y: viewport.height / 2 - centerY * zoom,
  };
}

export function reorderNode(nodes, id, direction) {
  const index = nodes.findIndex((node) => node.id === id);
  if (index < 0) return nodes;
  const target = clamp(index + direction, 0, nodes.length - 1);
  if (target === index) return nodes;
  const next = [...nodes];
  const [item] = next.splice(index, 1);
  next.splice(target, 0, item);
  return next;
}

export function duplicateNodes(nodes, selectedIds, offset = 32) {
  const selected = new Set(selectedIds);
  const copies = [];
  let serial = 0;
  for (const node of nodes) {
    if (!selected.has(node.id)) continue;
    serial += 1;
    copies.push({
      ...node,
      id: `${node.id}-copy-${Date.now()}-${serial}`,
      x: node.x + offset,
      y: node.y + offset,
      name: `${node.name ?? node.type} copy`,
    });
  }
  return copies;
}

export function createSeedNodes(count = 2000) {
  const nodes = [];
  const cols = Math.max(1, Math.ceil(Math.sqrt(count)));
  for (let index = 0; index < count; index += 1) {
    const col = index % cols;
    const row = Math.floor(index / cols);
    const type = index % 10 === 0 ? "text" : index % 7 === 0 ? "image" : "rect";
    const width = type === "text" ? 160 : type === "image" ? 144 : 112;
    const height = type === "text" ? 56 : type === "image" ? 108 : 88;
    nodes.push({
      id: `node-${index + 1}`,
      type,
      name: `${type}-${index + 1}`,
      x: col * 176,
      y: row * 132,
      width,
      height,
      rotation: 0,
      text: type === "text" ? `LUMI 文本 ${index + 1}` : undefined,
      assetRef: type === "image" ? `asset://spike/image-${index % 24}` : undefined,
      fill: type === "rect" ? 0x6d78ff : type === "image" ? 0xd9a441 : 0x20242c,
    });
  }
  return nodes;
}

export function cloneState(value) {
  return typeof structuredClone === "function"
    ? structuredClone(value)
    : JSON.parse(JSON.stringify(value));
}

export class CommandHistory {
  constructor(limit = 100) {
    this.limit = limit;
    this.undoStack = [];
    this.redoStack = [];
  }

  pushApplied(command) {
    this.undoStack.push(command);
    if (this.undoStack.length > this.limit) this.undoStack.shift();
    this.redoStack = [];
  }

  execute(command) {
    command.apply();
    this.pushApplied(command);
  }

  undo() {
    const command = this.undoStack.pop();
    if (!command) return false;
    command.revert();
    this.redoStack.push(command);
    return true;
  }

  redo() {
    const command = this.redoStack.pop();
    if (!command) return false;
    command.apply();
    this.undoStack.push(command);
    return true;
  }

  get canUndo() {
    return this.undoStack.length > 0;
  }

  get canRedo() {
    return this.redoStack.length > 0;
  }
}
