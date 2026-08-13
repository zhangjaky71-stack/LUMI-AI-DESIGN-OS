# ADR-0001 — Canvas Renderer Technology Spike

> Status: **ACCEPTED**  
> Date: `2026-08-13`  
> Node: `NODE-08`  
> Decision owner: LUMI AI Design OS architecture

## Context

LUMI requires a Lovart-class infinite design workspace with many heterogeneous objects, image-heavy projects, precise local editing, selection transforms, realtime overlays, and later Design IR/Artifact versioning. The rendering library must not become the persisted document model.

The spike compared three mainstream 2D approaches:

- PixiJS v8 / WebGL-first renderer;
- Konva 10 / react-konva 19 Canvas2D object model;
- Fabric.js 7 Canvas2D object/editor model.

Versions pinned for the NODE-08 comparison:

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

PixiJS provides a retained scene graph, WebGL/WebGPU renderer paths, events, Assets/texture lifecycle primitives, text renderers, and explicit culling/performance controls.

Strengths for LUMI:

- GPU-oriented rendering is aligned with image-heavy and large-canvas workloads.
- Renderer state can remain disposable beneath LUMI Design IR.
- Manual virtualization, batching, culling and texture lifecycle stay under LUMI control.
- React does not need to reconcile pointer-move-rate scene updates.
- DOM overlay can own text editing, IME, accessibility and floating UI.

Risks:

- Selection/transform/editor primitives are LUMI-owned rather than built in.
- Text metrics and DOM/GPU synchronization require explicit contracts.
- WebGPU is not selected as the sole production backend in this ADR.
- A naive one-DisplayObject-per-logical-node scene is not the production strategy for large scenes.

### Option B — Konva / react-konva

Konva provides a convenient interactive Canvas2D object model, events, shapes and editor-oriented abstractions.

Strengths:

- High-level interaction APIs accelerate conventional editor development.
- React integration is straightforward.
- Built-in transforms/events reduce custom plumbing.

Risks for LUMI:

- React → Konva → Canvas adds abstraction on high-frequency paths.
- Large image-heavy infinite-canvas usage still requires custom virtualization and lifecycle management.
- Konva serialization is intentionally not usable as LUMI persisted state.
- The retained Canvas2D object model is less aligned with the renderer-neutral Design IR boundary LUMI requires.

### Option C — Fabric.js

Fabric.js provides a rich Canvas2D editor object model with built-in transforms, filters, grouping and serialization/export helpers.

Strengths:

- Most conventional editor controls are available quickly.
- Rich object and serialization ecosystem.
- Strong fit for moderate-size conventional 2D editors.

Risks for LUMI:

- Object-model/Canvas2D coupling is stronger than desired for an independently versioned Design IR compiler.
- Built-in serialization is not a substitute for LUMI Artifact/Provenance semantics.
- Large image-heavy infinite canvas still needs custom virtualization/cache policies.
- Less aligned with the desired GPU-first media workspace direction.

## Spike architecture proven by NODE-08

```text
LUMI Scene/Camera/History/Asset Cache contracts
                    ↓ compile/sync
      disposable renderer scene state
                    ↓
      PixiJS WebGL viewport/batch layer

React shell / panels / selection metadata
                    ↓
DOM overlay: textarea + transform handles + accessibility
```

Boundary proven by the prototype:

```text
Persisted Design IR != Pixi Container tree
Undo/Redo history     != Pixi internal state
Asset identity        != GPU texture identity
Camera transform      != per-node persisted transform rewrite
```

## Evidence

### Interaction and lifecycle evidence

The executable `/canvas-spike` prototype and Playwright gate cover:

```text
pan
wheel zoom-to-cursor
pinch zoom
click/marquee/multi-select
multi-node drag
resize
rotate
layer reorder
copy/paste
undo/redo
DOM textarea text edit overlay
image assetRef display
viewport culling
thumbnail/preview/full cache tiers
ref-count + LRU eviction contract
2k / 10k shape stress
1k image stress
1k text + 100 rich-text stress
500 selected-node imperative drag
```

### Why raw headless FPS is not the renderer decision metric

The focused renderer comparison on GitHub Actions Headless Chrome 149 measured the browser's own empty `requestAnimationFrame` baseline at approximately:

```text
empty-rAF P50 = 50.0 ms
empty-rAF P95 = 50.1 ms
≈ 20.5 fps
```

Therefore this environment cannot certify a 16.7 ms / 60 fps workstation target even when the application does no rendering work.

The same run showed unstable absolute rAF rankings across Pixi, Konva and Fabric. Those numbers are retained as reproducible regression evidence, but they are not used as a fake hardware-performance certification.

### Synchronous workload evidence

To isolate LUMI/Pixi work from headless rAF throttling, NODE-08 measured synchronous:

```text
logical scan/cull
+ visible batch rebuild
+ Pixi renderer submission
```

on the same Headless Chrome 149 environment.

| Scenario | Logical nodes | Mean visible | P50 op ms | P95 op ms | Mean op ms |
|---|---:|---:|---:|---:|---:|
| Pixi batched sync 2k | 2,000 | 383.8 | 0.7 | **6.5** | 2.538 |
| Pixi batched sync 10k | 10,000 | 383.8 | 1.6 | **4.9** | 2.527 |

Both P95 operation times are below the 16.7 ms frame-work budget. This does **not** claim that a headless CI browser runs at 60 fps; it proves that the renderer-neutral cull/batch/submit architecture itself is not consuming the whole frame budget in the tested workload.

Primary evidence:

```text
Workflow: Canvas Renderer Fallback
Run: 31658264491
Artifact: canvas-renderer-fallback-31658264491
Artifact ID: 9165224796
SHA256: f6748ce16690562bbab6dcacd36bd820c0983068989a2bccdf2354c89381dafe
```

## Decision

**Accept PixiJS v8 + DOM overlay as the LUMI Canvas renderer baseline.**

Production architecture policy:

```text
Renderer baseline: PixiJS v8 / WebGL-first
Large-scene policy: logical scene != renderer-resident objects
Large shapes: batching / pooled visible representation
Images: viewport-aware progressive texture residency
React: shell/state bridge, never pointer-move-rate scene reconciler
Text edit: DOM overlay
Persisted document: LUMI Design IR / Artifact model, never Pixi serialization
WebGPU: optional future backend; promotion requires later compatibility/performance evidence
```

Konva and Fabric remain reference implementations and fallback candidates, but NODE-08 found no evidence strong enough to replace the Pixi baseline.

## Hardware performance gate

NODE-08 intentionally separates **technology selection** from **real workstation certification**.

The following remains mandatory before production release:

```text
Chrome current on representative Windows hardware
Edge current on representative Windows hardware
Safari current on representative macOS hardware when supported
DPR 1 / 2
2k mixed scene interactive P95 target near <= 16.7 ms
10k stress degradation measured and bounded
GPU/texture memory growth measured during long pan/zoom sessions
```

Ownership:

- NODE-40 — production Canvas Engine and browser support contract;
- NODE-69 — workstation performance, scalability and soak/capacity evidence.

A headless GitHub runner may be used for regression detection, but **must never be used to claim workstation 60 fps certification**.

## Consequences

- NODE-09 can proceed with renderer-neutral domain modeling.
- NODE-13 defines renderer-neutral Design IR.
- NODE-38 implements Design IR runtime/migrations.
- NODE-40 formalizes the Pixi dependency, viewport/batching/culling/selection engine and hardware browser gate.
- NODE-41 owns IR → renderer scene compilation.
- NODE-55 owns product-level infinite-canvas UX.
- NODE-56 owns layers/inspector.
- NODE-59 owns version UI independent of renderer state.

## First-party/public references retained by the spike

- PixiJS renderer guide: https://pixijs.com/8.x/guides/components/renderers
- PixiJS scene graph/culling: https://pixijs.com/8.x/guides/concepts/scene-graph
- PixiJS textures/assets: https://pixijs.com/8.x/guides/components/assets
- PixiJS performance tips: https://pixijs.com/8.x/guides/concepts/performance-tips
- Konva overview: https://konvajs.org/docs/overview.html
- Konva performance/layers: https://konvajs.org/docs/performance/Layer_Management.html
- react-konva: https://konvajs.org/docs/react/index.html
- Fabric.js docs: https://fabricjs.com/docs/
