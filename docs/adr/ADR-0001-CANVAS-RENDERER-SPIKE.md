# ADR-0001 — Canvas Renderer Technology Spike

> Status: **VALIDATING**  
> Date: `2026-08-13`  
> Node: `NODE-08`  
> Decision owner: LUMI AI Design OS architecture

## Context

LUMI requires a Lovart-class infinite design workspace with many heterogeneous objects, image-heavy projects, precise local editing, selection transforms, realtime overlays, and later Design IR/Artifact versioning. The rendering library must not become the persisted document model.

The spike compares three mainstream 2D approaches:

- PixiJS v8 / WebGL-first renderer;
- Konva 10 / react-konva 19 Canvas2D object model;
- Fabric.js 7 Canvas2D object/editor model.

Current public baseline versions observed on 2026-08-13:

```text
PixiJS      8.19.0
Konva       10.3.0
react-konva 19.2.5
Fabric.js   7.4.0
```

## Required LUMI characteristics

```text
10k simple-object stress visibility
2k mixed normal scene near-interactive frame cadence
1k image thumbnails with controlled lifecycle
1k text + 100 rich-text stress
500 selected nodes imperative transform
infinite pan + zoom-to-cursor + pinch
selection/marquee/multi-select
resize/rotate/layering
DOM text editor for IME/accessibility
explicit world/canvas/screen coordinate model
disposable renderer scene graph
asset cache/eviction control
future Design IR compiler compatibility
```

## Options

### Option A — PixiJS v8

Official PixiJS v8 documentation exposes a retained scene graph, event system, WebGL/WebGPU renderers, Assets/texture lifecycle APIs, garbage collection, Text/BitmapText/HTMLText, and application/manual culling patterns. Current renderer guidance recommends WebGL for production while WebGPU remains a future-facing option with browser consistency caveats.

Strengths for LUMI:

- GPU-oriented scene graph and batching fit large image/shape workloads.
- Renderer state can remain disposable beneath LUMI Design IR.
- Manual culling and texture lifecycle can be owned by LUMI.
- React does not need to own pointer-move-rate object transforms.
- DOM overlay can handle text editing/IME/accessibility without forcing all text interactions through GPU text.

Risks:

- Editor transforms/selection handles are not a built-in design-editor abstraction; LUMI must implement them.
- Text metrics and DOM/GPU synchronization require explicit contracts.
- WebGPU cannot yet be treated as the sole production renderer.
- Production package dependency is intentionally deferred to NODE-40 after this spike.

### Option B — Konva / react-konva

Konva provides an interactive Canvas2D object model with shapes, nesting, dragging/events, JSON serialization and performance tools such as caching/layer separation. react-konva provides declarative React bindings. Official Konva performance guidance emphasizes careful layer management and generally recommends only a few canvas layers.

Strengths:

- High-level interaction/object APIs are convenient for editor prototypes.
- React integration is mature and directly maps shapes to JSX.
- Built-in transforms/events reduce custom editor plumbing.

Risks for LUMI:

- React → Konva → Canvas layers add abstraction on high-frequency paths; react-konva itself notes vanilla canvas can be faster because of the extra layers.
- Canvas2D redraw strategy is less attractive for LUMI's image-heavy, very-large-workspace target.
- Konva JSON must not become the LUMI persisted document model, so much of its serialization convenience is intentionally unused.
- Layer-per-canvas optimization conflicts with the desire to keep a simple renderer topology at large scale.

### Option C — Fabric.js

Fabric.js provides a rich Canvas2D object model with out-of-box move/scale/rotate/skew/group controls, filters, brushes, and JSON/SVG/image I/O.

Strengths:

- Most editor-like controls are available quickly.
- Rich object and serialization ecosystem.
- Suitable for conventional 2D editors with moderate scene size.

Risks for LUMI:

- Canvas2D/object-model coupling is stronger than desired for an independently versioned Design IR compiler.
- Built-in serialization is not a substitute for LUMI Artifact/Provenance semantics.
- Large image-heavy infinite canvas still requires custom virtualization/cache policies.
- Less aligned with LUMI's GPU-first media workspace direction than Pixi.

## Spike architecture

NODE-08 implements:

```text
LUMI Scene/Camera/History/Asset Cache contracts
                    ↓ compile/sync
        disposable Pixi Scene Graph
                    ↓
          WebGL canvas renderer

React shell / panels / selection metadata
                    ↓
DOM overlay: textarea + transform handles + accessibility
```

Important boundary:

```text
Persisted Design IR != Pixi Container tree
Undo/Redo history     != Pixi internal state
Asset identity        != GPU texture identity
```

## Measurement plan

The blocking `canvas-spike` GitHub job opens `/canvas-spike` in Chromium and records:

```text
simple-2k
simple-10k
images-1k
text-1k-rich-100
selected-500-drag
```

P50/P95 requestAnimationFrame deltas and approximate FPS are written to `reports/canvas-spike/ci-headless.json` and Markdown. CI headless Chromium is treated as a reproducible regression environment, not representative desktop GPU certification.

The acceptance report will record the actual numbers from the clean PR run.

## Decision

**Conditional decision: adopt PixiJS v8 + DOM overlay as the NODE-40 Canvas Engine baseline if the NODE-08 interaction tests and browser stress evidence pass.**

Renderer policy:

```text
Production baseline: WebGL
WebGPU: optional/experimental until browser consistency and NODE-69 performance evidence justify promotion
React: shell/state bridge, not per-pointermove scene reconciler
Text editing: DOM overlay
Canvas persisted state: LUMI Design IR / Artifact model, never Pixi serialization
```

Konva and Fabric remain valid references for editor UX patterns but are not selected as the primary renderer architecture in this spike unless Pixi fails acceptance.

## Consequences

If accepted:

- NODE-13 defines renderer-neutral Design IR.
- NODE-38 implements Design IR runtime/migrations.
- NODE-40 formalizes the Pixi dependency, viewport/culling/selection engine and browser support contract.
- NODE-41 owns IR → Pixi scene compilation.
- NODE-55 owns product-level infinite-canvas UX.
- NODE-56 owns layers/inspector.
- NODE-59 owns version UI independent of renderer state.

If the clean spike misses critical interaction or severe 2k/10k performance expectations, this ADR remains unaccepted and NODE-08 must run a focused Konva/Fabric executable fallback spike before NODE-40.

## First-party/public sources

- PixiJS renderer guide: https://pixijs.com/8.x/guides/components/renderers
- PixiJS scene graph/culling: https://pixijs.com/8.x/guides/concepts/scene-graph
- PixiJS textures/assets: https://pixijs.com/8.x/guides/components/assets
- PixiJS performance tips: https://pixijs.com/8.x/guides/concepts/performance-tips
- Konva overview: https://konvajs.org/docs/overview.html
- Konva performance/layers: https://konvajs.org/docs/performance/Layer_Management.html
- react-konva: https://konvajs.org/docs/react/index.html
- Fabric.js docs: https://fabricjs.com/docs/
