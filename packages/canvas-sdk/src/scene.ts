import type { MutableSpikeNode, SpikeNode, TransformPatch } from "./types";

function cloneNode(node: SpikeNode): MutableSpikeNode {
  return { ...node };
}

export class SpikeSceneStore {
  readonly #nodes = new Map<string, MutableSpikeNode>();

  constructor(nodes: readonly SpikeNode[] = []) {
    for (const node of nodes) {
      this.#nodes.set(node.id, cloneNode(node));
    }
  }

  list(): SpikeNode[] {
    return [...this.#nodes.values()]
      .map((node) => ({ ...node }))
      .sort((a, b) => a.zIndex - b.zIndex || a.id.localeCompare(b.id));
  }

  get(id: string): SpikeNode | null {
    const node = this.#nodes.get(id);
    return node ? { ...node } : null;
  }

  add(node: SpikeNode): void {
    if (this.#nodes.has(node.id)) {
      throw new Error(`node already exists: ${node.id}`);
    }
    this.#nodes.set(node.id, cloneNode(node));
  }

  remove(id: string): SpikeNode | null {
    const node = this.#nodes.get(id);
    if (!node) {
      return null;
    }
    this.#nodes.delete(id);
    return { ...node };
  }

  patch(
    id: string,
    patch: TransformPatch & { readonly text?: string },
  ): SpikeNode {
    const node = this.#nodes.get(id);
    if (!node) {
      throw new Error(`node not found: ${id}`);
    }
    Object.assign(node, patch);
    return { ...node };
  }

  translate(ids: readonly string[], dx: number, dy: number): void {
    for (const id of ids) {
      const node = this.#nodes.get(id);
      if (node) {
        node.x += dx;
        node.y += dy;
      }
    }
  }

  reorder(id: string, zIndex: number): void {
    const node = this.#nodes.get(id);
    if (!node) {
      throw new Error(`node not found: ${id}`);
    }
    node.zIndex = zIndex;
  }

  duplicate(ids: readonly string[], offset = 24): SpikeNode[] {
    const copies: SpikeNode[] = [];
    for (const id of ids) {
      const source = this.#nodes.get(id);
      if (!source) {
        continue;
      }
      let suffix = 1;
      let nextId = `${source.id}-copy-${suffix}`;
      while (this.#nodes.has(nextId)) {
        suffix += 1;
        nextId = `${source.id}-copy-${suffix}`;
      }
      const copy: MutableSpikeNode = {
        ...source,
        id: nextId,
        x: source.x + offset,
        y: source.y + offset,
        zIndex: source.zIndex + suffix,
      };
      this.#nodes.set(copy.id, copy);
      copies.push({ ...copy });
    }
    return copies;
  }

  replaceAll(nodes: readonly SpikeNode[]): void {
    this.#nodes.clear();
    for (const node of nodes) {
      this.#nodes.set(node.id, cloneNode(node));
    }
  }
}

export function createSpikeSeedScene(): SpikeNode[] {
  return [
    {
      id: "frame-hero",
      kind: "frame",
      x: 80,
      y: 80,
      width: 720,
      height: 960,
      rotation: 0,
      zIndex: 0,
      fill: 0xf4f4f2,
    },
    {
      id: "rect-accent",
      kind: "rect",
      x: 140,
      y: 150,
      width: 230,
      height: 28,
      rotation: 0,
      zIndex: 1,
      fill: 0x202020,
    },
    {
      id: "text-title",
      kind: "text",
      x: 140,
      y: 215,
      width: 480,
      height: 130,
      rotation: 0,
      zIndex: 2,
      text: "LUMI 设计画布\nCanvas Spike 中文输入 🧪",
      fill: 0x111111,
    },
    {
      id: "image-product",
      kind: "image",
      x: 170,
      y: 420,
      width: 500,
      height: 360,
      rotation: 0,
      zIndex: 3,
      assetRef: "asset://product-reference-v1",
    },
  ];
}
