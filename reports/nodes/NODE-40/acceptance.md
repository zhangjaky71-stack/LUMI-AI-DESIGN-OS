# NODE-40 Acceptance — Canvas Engine V1

## Status

`IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL`

NODE-40 is stacked on `feat/node-39-constraint-validator`. Hosted GitHub Actions PASS is not claimed.

## Delivered

- renderer-neutral Canvas controller/domain runtime;
- NODE-38 Design IR operation gateway using `applyOperation` / `applyBatch`;
- NODE-39 constraint preflight passthrough and transform rollback;
- infinite-space camera math, zoom-to-cursor, fit, DPR state;
- scene projection for V1 node kinds with malformed-node isolation;
- point hit testing, multi-select, marquee, select-through and isolation boundary;
- locked-node transform protection;
- local move/resize/rotate preview and atomic commit;
- world-space snapping with nearby/grid guides;
- Chinese IME-safe text edit state and grapheme handling;
- authorized asset resolver + preview/full texture lifecycle + ref-counted LRU;
- internal Design IR fragment clipboard and cross-project asset remap policy;
- command history with constrained/versioned undo/redo replay;
- keyboard command guard for editable DOM targets;
- viewport culling and injectable rAF scheduler;
- headless renderer plus PixiJS v8 binding adapter boundary;
- 2k/10k structural benchmark harness;
- Vitest contract suite, static validator, dedicated CI and production gap ledger.

## Local evidence

The exact NODE-40 candidate source was exercised in an isolated workspace.

```text
NODE40_TS_STRICT_COMPILE_PASS
NODE40_TS_TEST_SUITE_STRICT_COMPILE_PASS
NODE40_RUNTIME_SMOKE_PASS
NODE40_CANVAS_ENGINE_VALIDATION_PASS
```

Local compiler version was TypeScript 5.8.3 with the repository's strict options reproduced. Repository TypeScript 6.0.3 / pnpm 11 / Vitest execution / root Prettier are not claimed locally; the hosted workflow owns those release gates.

Structural reference only:

```text
2,000 nodes: build ~= 5.42 ms; viewport query ~= 0.18 ms; visible=304
10,000 nodes: build ~= 15.31 ms; viewport query ~= 0.54 ms; visible=304
```

These are CPU structural/culling measurements in the current container, not browser frame time, GPU memory or a 60fps claim.

## Hosted runner evidence

The first dedicated workflow attempt for PR #107 is run `32012908687`. Its `canvas-engine` job `95336136979` ended before runner allocation with:

```text
status=completed
conclusion=failure
runner_id=0
runner_name=""
steps=[]
```

No checkout, Node setup, frozen pnpm install, repository TypeScript 6.0.3 typecheck, Vitest, Python setup, static validator, gap parse or lock reproducibility step executed. This is classified as `BLOCKED_EXTERNAL`, consistent with the runner-allocation blocker on preceding nodes. It is not a NODE-40 code or test failure.

## Correctness assertions

- camera state is never written into Design IR node transforms;
- renderer objects are never persisted in Design IR;
- transform preview is local until pointer-up commit;
- rejected constraints leave Design IR unchanged and reset preview;
- locked nodes cannot begin transform sessions;
- multi-node move commits as one Design IR batch;
- IME composition cannot commit partial Chinese text;
- clipboard asset IDs are re-authorized/remapped across projects;
- texture entries destroy zero-ref LRU resources and all resources on teardown;
- malformed or unsupported nodes degrade to placeholders/diagnostics instead of crashing the canvas;
- undo/redo replay through the operation gateway and therefore do not bypass constraints/version checks.

## Production qualification

Five production gaps remain explicitly open:

1. pinned PixiJS v8 browser bundle/workspace dependency wiring;
2. Playwright browser interaction E2E including Chinese IME and pinch/resize/DPR;
3. real GPU texture lifecycle instrumentation/leak tests;
4. NODE-08 standard-machine browser/GPU performance gate and near-60fps evidence;
5. Safari/macOS validation.

See `reports/nodes/NODE-40/gap-ledger.json`.

## Hosted acceptance gate

Before NODE-40 can become COMPLETE, an allocated runner must execute frozen pnpm install, repository TypeScript 6.0.3 typecheck, Vitest NODE-40 suite, static validation, lock-file checks and the relevant repository-wide frontend gates. Browser/GPU-specific gaps must then be closed separately rather than inferred from headless tests.

Next node: **NODE-41 — Canvas Compiler**.
