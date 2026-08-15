# NODE-08 — Acceptance Evidence

> Status: VALIDATING  
> Branch: `feat/node-08-canvas-spike`  
> Node: Canvas Technology Spike  
> Date: 2026-08-16

## Scope implemented

The branch contains an isolated PixiJS v8 browser technology spike and does not introduce Pixi runtime objects into persisted/domain data.

Implemented surfaces:

- renderer-independent `SpikeNode`-shaped JSON state and camera math;
- `worldToScreen` / `screenToWorld` coordinate conversion;
- zoom-to-cursor and wheel/pinch zoom;
- infinite pan;
- click selection, Shift-marquee multi-select, drag;
- resize and rotate controls;
- frame-selection / fit-scene;
- layer reorder;
- copy/paste;
- bounded undo/redo command history;
- DOM text editing with composition events, CJK, emoji, and multiline support;
- image asset references with lazy generated preview textures;
- offscreen culling and explicit texture release;
- selected image reference telemetry;
- browser benchmark scenarios for 2k mixed, 10k simple, 1k images, 1k text including 100 HTMLText nodes, and 500 selected-node transforms.

## Deterministic acceptance

`apps/web/public/canvas-spike/engine.test.mjs` validates:

1. coordinate round-trip precision;
2. zoom-to-cursor anchor preservation and zoom bounds;
3. marquee/culling geometry;
4. immutable selection translation, resize, and rotation transforms;
5. 500-node selection bounds and fit-camera behavior in a 2k seed scene;
6. undo/redo command behavior.

Command used by the NODE-08 workflow:

```bash
node --test apps/web/public/canvas-spike/engine.test.mjs
```

## Browser acceptance

`apps/web/e2e/canvas-spike.spec.ts` validates in Chromium:

- Pixi boot and 2,000-node seed scene;
- persisted spike node data contains no Pixi runtime object;
- zoom and pan interactions;
- DOM CJK/emoji/multiline edit and undo/redo;
- resize and rotate interaction;
- copy/paste and layer-order commands;
- measured benchmark scenario counts and finite frame-time data;
- texture pool release reaches zero after benchmark teardown.

Runtime benchmark JSON is written during CI to:

```text
reports/nodes/NODE-08/runtime/browser-benchmark.json
```

and uploaded as the workflow artifact `node-08-canvas-spike-<run_id>`.

## CI evidence

Pending first clean pull-request run. This section will be finalized after the branch passes the repository CI, secret scan, dependency review, and dedicated NODE-08 Canvas Spike workflow.

## Architecture evidence

ADR: `docs/adr/0001-canvas-renderer-baseline.md`

Decision: keep PixiJS v8 as the primary renderer baseline with a DOM overlay layer and strict renderer/domain separation; Konva remains the first fallback if a reproducible NODE-47-level blocker appears.

## Acceptance checklist

- [ ] Repository frontend gate passes.
- [ ] Repository Python gate passes.
- [ ] Repository contracts gate passes.
- [ ] Repository integration gate passes.
- [ ] Repository eval-smoke gate passes.
- [ ] Secret scan passes.
- [ ] Dependency review passes.
- [ ] NODE-08 deterministic engine tests pass.
- [ ] NODE-08 browser interaction suite passes.
- [ ] NODE-08 benchmark artifact is generated.
- [ ] Measured 10k stress data exists in the artifact.
- [ ] Texture resource release is verified by the browser test.

Until those checks are green, NODE-08 remains `VALIDATING`, not `COMPLETE`.
