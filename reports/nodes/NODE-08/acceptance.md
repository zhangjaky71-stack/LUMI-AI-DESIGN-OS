# NODE-08 — Acceptance Evidence

> Status: **BLOCKED_EXTERNAL / VALIDATING**  
> Branch: `feat/node-08-canvas-spike`  
> Pull Request: `#74`  
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

Workflow command:

```bash
node --test apps/web/public/canvas-spike/engine.test.mjs
```

Because GitHub-hosted Actions never allocated a runner, the same deterministic test file was executed in the available validation container as a fallback. Result: **6/6 PASS, 0 failures**. Evidence is committed at:

```text
reports/nodes/NODE-08/local-engine-test.txt
```

The fallback container exposed Node.js `v22.16.0`; repository CI remains pinned to Node 24 and must still run before this Node can be marked `COMPLETE`.

## Browser acceptance

`apps/web/e2e/canvas-spike.spec.ts` is prepared to validate in Chromium:

- Pixi boot and 2,000-node seed scene;
- persisted spike node data contains no Pixi runtime object;
- zoom and pan interactions;
- DOM CJK/emoji/multiline edit and undo/redo;
- resize and rotate interaction;
- copy/paste and layer-order commands;
- measured benchmark scenario counts and finite frame-time data;
- texture pool release reaches zero after benchmark teardown.

Runtime benchmark JSON is designed to be written during CI to:

```text
reports/nodes/NODE-08/runtime/browser-benchmark.json
```

and uploaded as the workflow artifact `node-08-canvas-spike-<run_id>`.

This browser acceptance is **NOT claimed as passed** while GitHub Actions is blocked before runner allocation.

## GitHub Actions evidence

PR `#74` head initially triggered these workflow runs:

```text
CI                    31896059237  FAILURE before runner allocation
NODE-08 Canvas Spike  31896059259  FAILURE before runner allocation
Secret Scan           31896059270  FAILURE before runner allocation
CodeQL                 31896059283  SKIPPED
Dependency Review      31896059324  FAILURE before useful execution
```

The dedicated NODE-08 job `95039441442` completed in approximately three seconds with:

```text
runner_id = 0
steps = []
```

GitHub check annotation:

```text
The job was not started because recent account payments have failed
or your spending limit needs to be increased. Please check the
'Billing & plans' section in your settings.
```

The repository-wide CI `changes` job `95039441550` failed in the same pre-runner manner with the same GitHub billing/spending-limit annotation. Therefore this is classified according to `docs/IMPLEMENTATION-PROTOCOL.md` as `BLOCKED_EXTERNAL`, not a code/test failure.

Required recovery after GitHub billing/spending limit is restored:

1. re-run PR `#74` checks;
2. require repository CI/security gates green;
3. require dedicated NODE-08 browser suite green;
4. retain the generated measured benchmark artifact;
5. only then update NODE-08 and `docs/NODE-INDEX.md` to `COMPLETE` and merge.

## Architecture evidence

ADR: `docs/adr/0001-canvas-renderer-baseline.md`

Decision: keep PixiJS v8 as the primary renderer baseline with a DOM overlay layer and strict renderer/domain separation; Konva remains the first fallback if a reproducible NODE-47-level blocker appears.

## Acceptance checklist

- [ ] Repository frontend gate passes — `BLOCKED_EXTERNAL`.
- [ ] Repository Python gate passes — `BLOCKED_EXTERNAL`.
- [ ] Repository contracts gate passes — `BLOCKED_EXTERNAL`.
- [ ] Repository integration gate passes — `BLOCKED_EXTERNAL`.
- [ ] Repository eval-smoke gate passes — `BLOCKED_EXTERNAL`.
- [ ] Secret scan passes — `BLOCKED_EXTERNAL`.
- [ ] Dependency review passes — `BLOCKED_EXTERNAL`.
- [x] NODE-08 deterministic engine tests pass locally: 6/6.
- [ ] NODE-08 browser interaction suite passes — `BLOCKED_EXTERNAL`.
- [ ] NODE-08 benchmark artifact is generated — `BLOCKED_EXTERNAL`.
- [ ] Measured 10k stress data exists in the artifact — `BLOCKED_EXTERNAL`.
- [ ] Texture resource release is verified by browser test — `BLOCKED_EXTERNAL`.

NODE-08 is implemented but remains **`BLOCKED_EXTERNAL / VALIDATING`**, not `COMPLETE`, until GitHub-hosted validation can execute.
