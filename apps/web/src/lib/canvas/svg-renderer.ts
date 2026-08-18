import type {
  RenderNodeSnapshot,
  RendererAdapter,
  RendererFrame,
} from "@lumi/canvas-sdk";

const SVG_NS = "http://www.w3.org/2000/svg";

export class SvgCanvasRenderer implements RendererAdapter {
  private readonly nodes = new Map<string, SVGGElement>();

  constructor(private readonly svg: SVGSVGElement) {}

  mount(): void {
    this.svg.setAttribute("role", "application");
    this.svg.setAttribute("aria-label", "LUMI infinite canvas");
    this.svg.setAttribute("tabindex", "0");
  }

  render(frame: RendererFrame): void {
    this.svg.setAttribute("viewBox", `0 0 ${frame.viewport.width} ${frame.viewport.height}`);
    const visible = new Set<string>();
    for (const node of frame.visibleNodes) {
      if (!node.visible) continue;
      visible.add(node.id);
      let group = this.nodes.get(node.id);
      if (!group) {
        group = document.createElementNS(SVG_NS, "g");
        group.dataset.nodeId = node.id;
        group.style.cursor = node.locked ? "not-allowed" : "move";
        this.svg.append(group);
        this.nodes.set(node.id, group);
      }
      drawNode(group, node, frame);
    }
    for (const [nodeId, group] of this.nodes) {
      if (visible.has(nodeId)) continue;
      group.remove();
      this.nodes.delete(nodeId);
    }
  }

  destroyNode(nodeId: string): void {
    this.nodes.get(nodeId)?.remove();
    this.nodes.delete(nodeId);
  }

  destroy(): void {
    for (const group of this.nodes.values()) group.remove();
    this.nodes.clear();
  }
}

function drawNode(
  group: SVGGElement,
  node: RenderNodeSnapshot,
  frame: RendererFrame,
): void {
  while (group.firstChild) group.firstChild.remove();
  const zoom = frame.camera.zoom;
  const x = (node.bounds.x - frame.camera.x) * zoom;
  const y = (node.bounds.y - frame.camera.y) * zoom;
  const width = Math.max(1, node.bounds.width * zoom);
  const height = Math.max(1, node.bounds.height * zoom);
  group.setAttribute(
    "transform",
    `translate(${x} ${y}) rotate(${node.rotationDeg} ${width / 2} ${height / 2})`,
  );
  group.setAttribute("opacity", String(node.opacity));
  group.dataset.locked = node.locked ? "true" : "false";

  const rect = document.createElementNS(SVG_NS, "rect");
  rect.setAttribute("width", String(width));
  rect.setAttribute("height", String(height));
  rect.setAttribute("rx", node.kind === "FRAME" ? "4" : "2");
  rect.setAttribute("fill", fillFor(node.kind));
  rect.setAttribute(
    "stroke",
    frame.selectedIds.has(node.id) ? "#2563eb" : strokeFor(node.kind),
  );
  rect.setAttribute("stroke-width", frame.selectedIds.has(node.id) ? "2" : "1");
  rect.setAttribute("vector-effect", "non-scaling-stroke");
  group.append(rect);

  if (node.kind === "TEXT" && node.text && zoom >= 0.18) {
    const text = document.createElementNS(SVG_NS, "text");
    text.setAttribute("x", "6");
    text.setAttribute("y", String(Math.min(height - 4, 18)));
    text.setAttribute("font-size", String(Math.max(9, Math.min(16, 13 * zoom))));
    text.setAttribute("fill", "#18181b");
    text.setAttribute("pointer-events", "none");
    text.textContent = truncate(node.text, 72);
    group.append(text);
  } else if ((node.kind === "IMAGE" || node.kind === "PLACEHOLDER") && zoom >= 0.22) {
    const label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("x", String(width / 2));
    label.setAttribute("y", String(height / 2));
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("dominant-baseline", "middle");
    label.setAttribute("font-size", String(Math.max(9, Math.min(13, 11 * zoom))));
    label.setAttribute("fill", "#71717a");
    label.setAttribute("pointer-events", "none");
    label.textContent = node.kind === "IMAGE" ? "IMAGE" : "UNSUPPORTED";
    group.append(label);
  }

  if (node.locked) {
    const lock = document.createElementNS(SVG_NS, "circle");
    lock.setAttribute("cx", String(Math.max(7, width - 7)));
    lock.setAttribute("cy", "7");
    lock.setAttribute("r", "3");
    lock.setAttribute("fill", "#f59e0b");
    lock.setAttribute("pointer-events", "none");
    group.append(lock);
  }
}

function fillFor(kind: RenderNodeSnapshot["kind"]): string {
  if (kind === "FRAME") return "#ffffff";
  if (kind === "TEXT") return "rgba(255,255,255,.72)";
  if (kind === "IMAGE") return "#e4e4e7";
  if (kind === "SHAPE" || kind === "VECTOR_PATH") return "#dbeafe";
  if (kind === "PLACEHOLDER") return "#fef3c7";
  return "rgba(244,244,245,.68)";
}

function strokeFor(kind: RenderNodeSnapshot["kind"]): string {
  if (kind === "FRAME") return "#d4d4d8";
  if (kind === "PLACEHOLDER") return "#f59e0b";
  return "rgba(63,63,70,.18)";
}

function truncate(value: string, length: number): string {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}
