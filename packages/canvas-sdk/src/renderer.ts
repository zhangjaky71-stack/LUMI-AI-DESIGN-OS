import type { RendererAdapter, RendererFrame } from "./types";

export class HeadlessRendererAdapter implements RendererAdapter {
  lastFrame: RendererFrame | null = null;
  readonly destroyedNodes: string[] = [];
  mounted = false;
  destroyed = false;
  mount(): void { this.mounted = true; }
  render(frame: RendererFrame): void { if (this.destroyed) throw new Error("CANVAS_RENDERER_DESTROYED"); this.lastFrame = frame; }
  destroyNode(nodeId: string): void { this.destroyedNodes.push(nodeId); }
  destroy(): void { this.destroyed = true; this.lastFrame = null; }
}

export interface PixiV8Bindings {
  mount(): void | Promise<void>;
  syncNode(node: RendererFrame["visibleNodes"][number]): void;
  removeNode(nodeId: string): void;
  setCamera(frame: Pick<RendererFrame, "camera" | "viewport">): void;
  setSelection(ids: ReadonlySet<string>): void;
  render(): void;
  destroy(): void;
}

export class PixiV8RendererAdapter implements RendererAdapter {
  private visible = new Set<string>();
  constructor(private readonly bindings: PixiV8Bindings) {}
  mount(): void | Promise<void> { return this.bindings.mount(); }
  render(frame: RendererFrame): void {
    this.bindings.setCamera(frame);
    const next = new Set(frame.visibleNodes.map((node) => node.id));
    for (const id of this.visible) if (!next.has(id)) this.bindings.removeNode(id);
    for (const node of frame.visibleNodes) this.bindings.syncNode(node);
    this.bindings.setSelection(frame.selectedIds);
    this.bindings.render();
    this.visible = next;
  }
  destroyNode(nodeId: string): void { this.visible.delete(nodeId); this.bindings.removeNode(nodeId); }
  destroy(): void { this.visible.clear(); this.bindings.destroy(); }
}
