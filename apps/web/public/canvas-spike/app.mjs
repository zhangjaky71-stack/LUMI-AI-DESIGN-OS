import {
  Application,
  Container,
  HTMLText,
  Sprite,
  Text,
  Texture,
} from "https://cdn.jsdelivr.net/npm/pixi.js@8.18.1/dist/pixi.min.mjs";
import {
  CommandHistory,
  MAX_ZOOM,
  MIN_ZOOM,
  cloneState,
  createSeedNodes,
  cullNodeIds,
  duplicateNodes,
  fitCameraToRect,
  marqueeSelect,
  reorderNode,
  resizeNode,
  rotateNodeToPointer,
  screenToWorld,
  selectionBounds,
  translateNodes,
  worldToScreen,
  zoomAtScreenPoint,
} from "./engine.mjs";

const host = document.querySelector("#canvas-host");
const statusEl = document.querySelector("#status");
const rendererEl = document.querySelector("#renderer");
const cameraEl = document.querySelector("#camera");
const nodeCountEl = document.querySelector("#node-count");
const visibleCountEl = document.querySelector("#visible-count");
const selectedCountEl = document.querySelector("#selected-count");
const imageRefEl = document.querySelector("#image-ref");
const textureCountEl = document.querySelector("#texture-count");
const selectionBox = document.querySelector("#selection-box");
const marqueeEl = document.querySelector("#marquee");
const textEditor = document.querySelector("#text-editor");
const benchmarkOutput = document.querySelector("#benchmark-output");

const app = new Application();
await app.init({
  resizeTo: host,
  background: "#101216",
  antialias: false,
  autoDensity: true,
  resolution: Math.min(window.devicePixelRatio || 1, 2),
  preference: "webgl",
});
host.appendChild(app.canvas);
app.canvas.style.touchAction = "none";

const world = new Container({ sortableChildren: true });
world.sortableChildren = true;
app.stage.addChild(world);
app.stage.eventMode = "static";
app.stage.hitArea = app.screen;

let camera = { x: 120, y: 90, zoom: 0.7 };
let nodes = createSeedNodes(2000);
let selectedIds = ["node-1"];
let copiedNodes = [];
let dragState = null;
let backgroundState = null;
let composing = false;
let editorNodeId = null;
let visibleIds = new Set();
const history = new CommandHistory(100);
const displayById = new Map();
const imageMetaById = new Map();

class TexturePool {
  constructor(maxEntries = 32) {
    this.maxEntries = maxEntries;
    this.entries = new Map();
  }

  acquire(key) {
    let entry = this.entries.get(key);
    if (!entry) {
      const canvas = document.createElement("canvas");
      canvas.width = 128;
      canvas.height = 96;
      const ctx = canvas.getContext("2d");
      const hue = Math.abs(hashString(key)) % 360;
      const gradient = ctx.createLinearGradient(0, 0, 128, 96);
      gradient.addColorStop(0, `hsl(${hue} 65% 60%)`);
      gradient.addColorStop(1, `hsl(${(hue + 48) % 360} 55% 30%)`);
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, 128, 96);
      ctx.fillStyle = "rgba(255,255,255,.86)";
      ctx.font = "600 14px system-ui";
      ctx.fillText("LUMI", 10, 22);
      entry = { texture: Texture.from(canvas), refs: 0, touched: performance.now() };
      this.entries.set(key, entry);
    }
    entry.refs += 1;
    entry.touched = performance.now();
    this.evict();
    return entry.texture;
  }

  release(key) {
    const entry = this.entries.get(key);
    if (!entry) return;
    entry.refs = Math.max(0, entry.refs - 1);
    entry.touched = performance.now();
    this.evict();
  }

  evict() {
    if (this.entries.size <= this.maxEntries) return;
    const candidates = [...this.entries.entries()]
      .filter(([, value]) => value.refs === 0)
      .sort((a, b) => a[1].touched - b[1].touched);
    while (this.entries.size > this.maxEntries && candidates.length > 0) {
      const [key, entry] = candidates.shift();
      entry.texture.destroy(true);
      this.entries.delete(key);
    }
  }

  clearUnused() {
    for (const [key, entry] of [...this.entries.entries()]) {
      if (entry.refs === 0) {
        entry.texture.destroy(true);
        this.entries.delete(key);
      }
    }
  }

  destroyAll() {
    for (const entry of this.entries.values()) entry.texture.destroy(true);
    this.entries.clear();
  }

  get size() {
    return this.entries.size;
  }
}

const texturePool = new TexturePool(32);

function hashString(value) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) hash = (hash * 31 + value.charCodeAt(index)) | 0;
  return hash;
}

function makeDisplay(node) {
  const container = new Container();
  container.eventMode = "static";
  container.cursor = "move";
  container.label = node.id;

  const background = new Sprite(Texture.WHITE);
  background.alpha = node.type === "text" ? 0.18 : 1;
  background.tint = node.fill ?? 0x59657a;
  container.addChild(background);

  let label = null;
  if (node.type === "text") {
    label = new Text({
      text: node.text ?? "Text",
      style: { fill: "#f6f7fb", fontSize: 18, fontFamily: "Arial, sans-serif", wordWrap: true },
    });
    label.x = 10;
    label.y = 8;
    container.addChild(label);
  } else if (node.type === "image") {
    label = new Text({
      text: "IMAGE",
      style: { fill: "rgba(255,255,255,.92)", fontSize: 13, fontWeight: "600", fontFamily: "Arial, sans-serif" },
    });
    label.x = 10;
    label.y = 8;
    container.addChild(label);
    imageMetaById.set(node.id, { sprite: background, loadedRef: null });
  }

  container.on("pointerdown", (event) => {
    event.stopPropagation();
    if (!selectedIds.includes(node.id)) {
      selectedIds = event.shiftKey ? [...selectedIds, node.id] : [node.id];
      updateSelectionOverlay();
      updateTelemetry();
    }
    const startWorld = screenToWorld({ x: event.global.x, y: event.global.y }, camera);
    dragState = {
      startWorld,
      before: cloneState(nodes),
      selected: [...selectedIds],
      moved: false,
    };
  });

  container.on("pointertap", (event) => {
    if (event.detail >= 2 && node.type === "text") openTextEditor(node.id);
  });

  world.addChild(container);
  displayById.set(node.id, container);
  syncDisplay(node);
  return container;
}

function syncDisplay(node) {
  let container = displayById.get(node.id);
  if (!container) container = makeDisplay(node);
  container.position.set(node.x + node.width / 2, node.y + node.height / 2);
  container.pivot.set(node.width / 2, node.height / 2);
  container.rotation = node.rotation || 0;
  const background = container.children[0];
  background.width = node.width;
  background.height = node.height;
  if (node.type === "text" && container.children[1]) {
    container.children[1].text = node.text ?? "Text";
    container.children[1].style.wordWrapWidth = Math.max(24, node.width - 20);
  }
}

function rebuildDisplays() {
  const valid = new Set(nodes.map((node) => node.id));
  for (const [id, display] of [...displayById.entries()]) {
    if (!valid.has(id)) {
      const imageMeta = imageMetaById.get(id);
      if (imageMeta?.loadedRef) texturePool.release(imageMeta.loadedRef);
      imageMetaById.delete(id);
      display.destroy({ children: true });
      displayById.delete(id);
    }
  }
  nodes.forEach((node, index) => {
    syncDisplay(node);
    const display = displayById.get(node.id);
    display.zIndex = index;
  });
  updateCulling();
}

function applyCamera() {
  world.position.set(camera.x, camera.y);
  world.scale.set(camera.zoom);
  updateCulling();
  updateSelectionOverlay();
  updateTextEditorPosition();
  updateTelemetry();
}

function updateCulling() {
  visibleIds = cullNodeIds(
    nodes,
    camera,
    { width: host.clientWidth, height: host.clientHeight },
    180,
  );
  for (const node of nodes) {
    const display = displayById.get(node.id);
    if (!display) continue;
    const shouldShow = visibleIds.has(node.id);
    display.visible = shouldShow;
    if (node.type === "image") {
      const meta = imageMetaById.get(node.id);
      if (!meta) continue;
      if (shouldShow && !meta.loadedRef && node.assetRef) {
        meta.sprite.texture = texturePool.acquire(node.assetRef);
        meta.loadedRef = node.assetRef;
      } else if (!shouldShow && meta.loadedRef) {
        texturePool.release(meta.loadedRef);
        meta.sprite.texture = Texture.WHITE;
        meta.loadedRef = null;
      }
    }
  }
  texturePool.clearUnused();
  textureCountEl.textContent = String(texturePool.size);
}

function updateSelectionOverlay() {
  const bounds = selectionBounds(nodes, selectedIds);
  if (!bounds) {
    selectionBox.classList.add("hidden");
    return;
  }
  const topLeft = worldToScreen({ x: bounds.x, y: bounds.y }, camera);
  const bottomRight = worldToScreen({ x: bounds.x + bounds.width, y: bounds.y + bounds.height }, camera);
  selectionBox.style.left = `${topLeft.x}px`;
  selectionBox.style.top = `${topLeft.y}px`;
  selectionBox.style.width = `${Math.max(1, bottomRight.x - topLeft.x)}px`;
  selectionBox.style.height = `${Math.max(1, bottomRight.y - topLeft.y)}px`;
  selectionBox.classList.remove("hidden");
}

function updateTelemetry() {
  cameraEl.textContent = `${camera.x.toFixed(0)}, ${camera.y.toFixed(0)} @ ${(camera.zoom * 100).toFixed(0)}%`;
  nodeCountEl.textContent = String(nodes.length);
  visibleCountEl.textContent = String(visibleIds.size);
  selectedCountEl.textContent = String(selectedIds.length);
  const selectedImage = nodes.find((node) => selectedIds.includes(node.id) && node.type === "image");
  imageRefEl.textContent = selectedImage?.assetRef ?? "—";
  textureCountEl.textContent = String(texturePool.size);
  document.querySelector("#undo").disabled = !history.canUndo;
  document.querySelector("#redo").disabled = !history.canRedo;
}

function replaceNodes(next) {
  nodes = cloneState(next);
  selectedIds = selectedIds.filter((id) => nodes.some((node) => node.id === id));
  rebuildDisplays();
  updateSelectionOverlay();
  updateTelemetry();
}

function recordApplied(before, after, label) {
  history.pushApplied({
    label,
    apply: () => replaceNodes(after),
    revert: () => replaceNodes(before),
  });
  updateTelemetry();
}

function commitDrag() {
  if (!dragState) return;
  const state = dragState;
  dragState = null;
  if (state.moved) recordApplied(state.before, cloneState(nodes), "move selection");
}

app.stage.on("globalpointermove", (event) => {
  if (dragState) {
    const current = screenToWorld({ x: event.global.x, y: event.global.y }, camera);
    const delta = { x: current.x - dragState.startWorld.x, y: current.y - dragState.startWorld.y };
    nodes = translateNodes(dragState.before, dragState.selected, delta);
    dragState.moved = Math.abs(delta.x) + Math.abs(delta.y) > 0.5;
    for (const id of dragState.selected) {
      const node = nodes.find((item) => item.id === id);
      if (node) syncDisplay(node);
    }
    updateSelectionOverlay();
    updateTelemetry();
    return;
  }

  if (!backgroundState) return;
  if (backgroundState.kind === "pan") {
    camera = {
      ...camera,
      x: backgroundState.camera.x + (event.global.x - backgroundState.start.x),
      y: backgroundState.camera.y + (event.global.y - backgroundState.start.y),
    };
    applyCamera();
  } else if (backgroundState.kind === "marquee") {
    const start = backgroundState.start;
    const current = { x: event.global.x, y: event.global.y };
    const left = Math.min(start.x, current.x);
    const top = Math.min(start.y, current.y);
    marqueeEl.style.left = `${left}px`;
    marqueeEl.style.top = `${top}px`;
    marqueeEl.style.width = `${Math.abs(current.x - start.x)}px`;
    marqueeEl.style.height = `${Math.abs(current.y - start.y)}px`;
  }
});

app.stage.on("pointerdown", (event) => {
  if (event.shiftKey) {
    backgroundState = { kind: "marquee", start: { x: event.global.x, y: event.global.y } };
    marqueeEl.style.left = `${event.global.x}px`;
    marqueeEl.style.top = `${event.global.y}px`;
    marqueeEl.style.width = "0px";
    marqueeEl.style.height = "0px";
    marqueeEl.classList.remove("hidden");
  } else {
    backgroundState = {
      kind: "pan",
      start: { x: event.global.x, y: event.global.y },
      camera: { ...camera },
    };
  }
});

function finishBackground(event) {
  if (!backgroundState) return;
  if (backgroundState.kind === "marquee") {
    const startWorld = screenToWorld(backgroundState.start, camera);
    const endWorld = screenToWorld({ x: event.global.x, y: event.global.y }, camera);
    selectedIds = marqueeSelect(nodes, {
      x: startWorld.x,
      y: startWorld.y,
      width: endWorld.x - startWorld.x,
      height: endWorld.y - startWorld.y,
    });
    marqueeEl.classList.add("hidden");
    updateSelectionOverlay();
    updateTelemetry();
  }
  backgroundState = null;
}

app.stage.on("pointerup", (event) => {
  commitDrag();
  finishBackground(event);
});
app.stage.on("pointerupoutside", (event) => {
  commitDrag();
  finishBackground(event);
});

app.canvas.addEventListener(
  "wheel",
  (event) => {
    event.preventDefault();
    const rect = app.canvas.getBoundingClientRect();
    const anchor = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    const factor = Math.exp(-event.deltaY * 0.0015);
    camera = zoomAtScreenPoint(camera, anchor, camera.zoom * factor);
    applyCamera();
  },
  { passive: false },
);

const touches = new Map();
let pinchStart = null;
app.canvas.addEventListener("pointerdown", (event) => {
  if (event.pointerType !== "touch") return;
  touches.set(event.pointerId, { x: event.offsetX, y: event.offsetY });
  if (touches.size === 2) {
    const [a, b] = [...touches.values()];
    const midpoint = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    pinchStart = {
      distance: Math.hypot(a.x - b.x, a.y - b.y),
      camera: { ...camera },
      worldAnchor: screenToWorld(midpoint, camera),
    };
  }
});
app.canvas.addEventListener("pointermove", (event) => {
  if (!touches.has(event.pointerId)) return;
  touches.set(event.pointerId, { x: event.offsetX, y: event.offsetY });
  if (touches.size !== 2 || !pinchStart) return;
  event.preventDefault();
  const [a, b] = [...touches.values()];
  const midpoint = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  const distance = Math.hypot(a.x - b.x, a.y - b.y);
  const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, pinchStart.camera.zoom * (distance / Math.max(1, pinchStart.distance))));
  camera = {
    zoom,
    x: midpoint.x - pinchStart.worldAnchor.x * zoom,
    y: midpoint.y - pinchStart.worldAnchor.y * zoom,
  };
  applyCamera();
});
for (const eventName of ["pointerup", "pointercancel", "pointerleave"]) {
  app.canvas.addEventListener(eventName, (event) => {
    touches.delete(event.pointerId);
    if (touches.size < 2) pinchStart = null;
  });
}

function screenPointer(event) {
  const rect = host.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

for (const handle of document.querySelectorAll(".handle")) {
  handle.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (selectedIds.length !== 1) return;
    const id = selectedIds[0];
    const before = cloneState(nodes);
    const start = screenPointer(event);
    const handleName = handle.dataset.handle;

    const move = (moveEvent) => {
      const current = screenPointer(moveEvent);
      const delta = { x: (current.x - start.x) / camera.zoom, y: (current.y - start.y) / camera.zoom };
      nodes = before.map((node) => (node.id === id ? resizeNode(node, handleName, delta) : node));
      const next = nodes.find((node) => node.id === id);
      if (next) syncDisplay(next);
      updateSelectionOverlay();
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      recordApplied(before, cloneState(nodes), `resize ${handleName}`);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up, { once: true });
  });
}

document.querySelector(".rotate-handle").addEventListener("pointerdown", (event) => {
  event.preventDefault();
  event.stopPropagation();
  if (selectedIds.length !== 1) return;
  const id = selectedIds[0];
  const before = cloneState(nodes);
  const move = (moveEvent) => {
    const pointerWorld = screenToWorld(screenPointer(moveEvent), camera);
    nodes = before.map((node) => (node.id === id ? rotateNodeToPointer(node, pointerWorld) : node));
    const next = nodes.find((node) => node.id === id);
    if (next) syncDisplay(next);
    updateSelectionOverlay();
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    recordApplied(before, cloneState(nodes), "rotate");
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up, { once: true });
});

function frameRect(rect) {
  camera = fitCameraToRect(rect, { width: host.clientWidth, height: host.clientHeight }, 80);
  applyCamera();
}

document.querySelector("#fit-scene").addEventListener("click", () => {
  const allIds = nodes.map((node) => node.id);
  const bounds = selectionBounds(nodes, allIds);
  if (bounds) frameRect(bounds);
});

document.querySelector("#frame-selection").addEventListener("click", () => {
  const bounds = selectionBounds(nodes, selectedIds);
  if (bounds) frameRect(bounds);
});

document.querySelector("#bring-forward").addEventListener("click", () => {
  if (selectedIds.length !== 1) return;
  const before = cloneState(nodes);
  nodes = reorderNode(nodes, selectedIds[0], 1);
  rebuildDisplays();
  recordApplied(before, cloneState(nodes), "bring forward");
});

document.querySelector("#send-backward").addEventListener("click", () => {
  if (selectedIds.length !== 1) return;
  const before = cloneState(nodes);
  nodes = reorderNode(nodes, selectedIds[0], -1);
  rebuildDisplays();
  recordApplied(before, cloneState(nodes), "send backward");
});

document.querySelector("#copy").addEventListener("click", () => {
  copiedNodes = nodes.filter((node) => selectedIds.includes(node.id)).map((node) => cloneState(node));
});

document.querySelector("#paste").addEventListener("click", () => {
  if (copiedNodes.length === 0) return;
  const before = cloneState(nodes);
  const scratch = [...nodes, ...copiedNodes];
  const sourceIds = copiedNodes.map((node) => node.id);
  const copies = duplicateNodes(scratch, sourceIds, 36).slice(-copiedNodes.length);
  nodes = [...nodes, ...copies];
  selectedIds = copies.map((node) => node.id);
  rebuildDisplays();
  recordApplied(before, cloneState(nodes), "paste");
});

document.querySelector("#undo").addEventListener("click", () => history.undo());
document.querySelector("#redo").addEventListener("click", () => history.redo());

document.addEventListener("keydown", (event) => {
  const modifier = event.metaKey || event.ctrlKey;
  if (modifier && event.key.toLowerCase() === "z") {
    event.preventDefault();
    if (event.shiftKey) history.redo(); else history.undo();
  }
  if (modifier && event.key.toLowerCase() === "c") copiedNodes = nodes.filter((node) => selectedIds.includes(node.id)).map((node) => cloneState(node));
  if (modifier && event.key.toLowerCase() === "v") document.querySelector("#paste").click();
});

function openTextEditor(id) {
  const node = nodes.find((item) => item.id === id && item.type === "text");
  if (!node) return;
  selectedIds = [id];
  editorNodeId = id;
  textEditor.value = node.text ?? "";
  textEditor.classList.remove("hidden");
  updateTextEditorPosition();
  textEditor.focus();
  textEditor.select();
}

function updateTextEditorPosition() {
  if (!editorNodeId || textEditor.classList.contains("hidden")) return;
  const node = nodes.find((item) => item.id === editorNodeId);
  if (!node) return;
  const topLeft = worldToScreen({ x: node.x, y: node.y }, camera);
  textEditor.style.left = `${topLeft.x}px`;
  textEditor.style.top = `${topLeft.y}px`;
  textEditor.style.width = `${Math.max(120, node.width * camera.zoom)}px`;
  textEditor.style.height = `${Math.max(48, node.height * camera.zoom)}px`;
  textEditor.style.fontSize = `${Math.max(12, 18 * camera.zoom)}px`;
}

function commitTextEditor() {
  if (!editorNodeId || composing) return;
  const id = editorNodeId;
  const before = cloneState(nodes);
  nodes = nodes.map((node) => (node.id === id ? { ...node, text: textEditor.value } : node));
  const next = nodes.find((node) => node.id === id);
  if (next) syncDisplay(next);
  editorNodeId = null;
  textEditor.classList.add("hidden");
  recordApplied(before, cloneState(nodes), "edit text");
}

document.querySelector("#edit-text").addEventListener("click", () => {
  if (selectedIds.length === 1) openTextEditor(selectedIds[0]);
});
textEditor.addEventListener("compositionstart", () => { composing = true; });
textEditor.addEventListener("compositionend", () => { composing = false; });
textEditor.addEventListener("blur", () => commitTextEditor());
textEditor.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && !composing) {
    event.preventDefault();
    commitTextEditor();
  }
  if (event.key === "Escape") {
    editorNodeId = null;
    textEditor.classList.add("hidden");
  }
});

function percentile(values, p) {
  const sorted = [...values].sort((a, b) => a - b);
  if (sorted.length === 0) return 0;
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[index];
}

async function measureFrames(frameCount, onFrame) {
  const deltas = [];
  let previous = performance.now();
  for (let index = 0; index < frameCount; index += 1) {
    await new Promise((resolve) => requestAnimationFrame(resolve));
    const now = performance.now();
    deltas.push(now - previous);
    previous = now;
    onFrame?.(index);
  }
  return {
    samples: deltas.length,
    mean_ms: deltas.reduce((sum, value) => sum + value, 0) / Math.max(1, deltas.length),
    p95_ms: percentile(deltas, 95),
    max_ms: Math.max(...deltas),
  };
}

function benchSprite(color = 0x6674ff) {
  const sprite = new Sprite(Texture.WHITE);
  sprite.width = 64;
  sprite.height = 48;
  sprite.tint = color;
  return sprite;
}

async function runScenario(name, count, factory, columns = 100) {
  const bench = new Container();
  app.stage.addChild(bench);
  const startBuild = performance.now();
  let visible = 0;
  for (let index = 0; index < count; index += 1) {
    const item = factory(index);
    item.x = (index % columns) * 82;
    item.y = Math.floor(index / columns) * 64;
    const inView = item.x < host.clientWidth + 220 && item.y < host.clientHeight + 220;
    item.visible = inView;
    if (inView) visible += 1;
    bench.addChild(item);
  }
  const buildMs = performance.now() - startBuild;
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const frames = await measureFrames(90, (index) => {
    bench.x = Math.sin(index / 8) * 18;
    bench.y = Math.cos(index / 11) * 12;
  });
  bench.destroy({ children: true });
  return { name, count, visible_after_cull: visible, build_ms: buildMs, ...frames };
}

async function runBenchmark() {
  const button = document.querySelector("#run-benchmark");
  button.disabled = true;
  benchmarkOutput.textContent = "running…";
  const originalVisible = world.visible;
  world.visible = false;
  const benchmarkTexturePool = new TexturePool(24);
  const started = performance.now();

  try {
    const mixed = await runScenario("mixed2k", 2000, (index) => {
      if (index % 10 === 0) {
        const text = new Text({ text: `文本 ${index}`, style: { fill: "#fff", fontSize: 14, fontFamily: "Arial" } });
        text.scale.set(0.75);
        return text;
      }
      if (index % 7 === 0) {
        const sprite = benchSprite(0xffffff);
        sprite.texture = benchmarkTexturePool.acquire(`bench-image-${index % 24}`);
        return sprite;
      }
      return benchSprite(0x6674ff);
    }, 70);

    const simple = await runScenario("simple10k", 10000, () => benchSprite(0x4f5d73), 125);

    const images = await runScenario("images1k", 1000, (index) => {
      const sprite = benchSprite(0xffffff);
      sprite.texture = benchmarkTexturePool.acquire(`image-${index % 24}`);
      return sprite;
    }, 50);

    const text = await runScenario("text1k", 1000, (index) => {
      if (index < 100) {
        const rich = new HTMLText({
          text: `<b>Rich</b> <span style="color:#a39fff">${index}</span> 🙂`,
          style: { fill: "#fff", fontSize: 13, fontFamily: "Arial" },
        });
        rich.scale.set(0.7);
        return rich;
      }
      const label = new Text({ text: `Label ${index}`, style: { fill: "#fff", fontSize: 13, fontFamily: "Arial" } });
      label.scale.set(0.75);
      return label;
    }, 50);

    const selectionContainer = new Container();
    const selectionItems = [];
    for (let index = 0; index < 500; index += 1) {
      const sprite = benchSprite(0x8e80ff);
      sprite.x = (index % 25) * 40;
      sprite.y = Math.floor(index / 25) * 36;
      sprite.width = 30;
      sprite.height = 24;
      selectionItems.push(sprite);
      selectionContainer.addChild(sprite);
    }
    app.stage.addChild(selectionContainer);
    const selection = await measureFrames(90, (frame) => {
      const dx = Math.sin(frame / 7) * 0.8;
      for (const item of selectionItems) item.x += dx;
    });
    selectionContainer.destroy({ children: true });

    const texturesBeforeRelease = benchmarkTexturePool.size;
    benchmarkTexturePool.destroyAll();
    const texturesAfterRelease = benchmarkTexturePool.size;
    const memory = performance.memory
      ? {
          used_js_heap_mb: performance.memory.usedJSHeapSize / 1024 / 1024,
          total_js_heap_mb: performance.memory.totalJSHeapSize / 1024 / 1024,
        }
      : null;

    const result = {
      pixi_version: "8.18.1",
      renderer: rendererEl.textContent,
      dpr: app.renderer.resolution,
      viewport: { width: host.clientWidth, height: host.clientHeight },
      scenarios: { mixed2k: mixed, simple10k: simple, images1k: images, text1k: text, selection500: selection },
      resource_release: { textures_before_release: texturesBeforeRelease, textures_after_release: texturesAfterRelease },
      memory,
      elapsed_ms: performance.now() - started,
      measured_at: new Date().toISOString(),
    };
    window.__LUMI_CANVAS_METRICS__ = result;
    benchmarkOutput.textContent = JSON.stringify(result, null, 2);
    return result;
  } finally {
    benchmarkTexturePool.destroyAll();
    world.visible = originalVisible;
    button.disabled = false;
  }
}

document.querySelector("#run-benchmark").addEventListener("click", () => runBenchmark());

window.__LUMI_CANVAS_SPIKE__ = {
  get camera() { return { ...camera }; },
  get nodes() { return cloneState(nodes); },
  get selectedIds() { return [...selectedIds]; },
  runBenchmark,
  frameNode(id) {
    selectedIds = [id];
    const bounds = selectionBounds(nodes, selectedIds);
    if (bounds) frameRect(bounds);
    updateSelectionOverlay();
    updateTelemetry();
  },
  destroy() {
    texturePool.destroyAll();
    app.destroy(true, { children: true });
  },
};

window.addEventListener("resize", () => {
  app.stage.hitArea = app.screen;
  applyCamera();
});

rebuildDisplays();
applyCamera();
rendererEl.textContent = app.renderer.type === 1 ? "WebGL" : app.renderer.type === 2 ? "WebGPU" : `type-${app.renderer.type}`;
statusEl.textContent = "ready";
statusEl.dataset.ready = "true";
updateTelemetry();
