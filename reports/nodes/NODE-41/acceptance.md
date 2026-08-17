# NODE-41 Acceptance — Canvas Compiler V1

## Status

`IMPLEMENTED / VALIDATING`

NODE-41 is stacked on `feat/node-40-canvas-engine`. Hosted GitHub Actions PASS is not claimed until an allocated runner executes the dedicated workflow.

## Delivered

- Design IR -> renderer-neutral `CompiledSceneNode` compiler boundary;
- NODE-38 structural validation gate;
- deterministic hierarchical transform/world-bounds normalization;
- full compile with per-node diagnostics and placeholder isolation;
- incremental compile using NODE-38 SemanticDiff plus dependency expansion;
- resource-table change detection beyond node-level SemanticDiff;
- mask/clip/group/frame dependency dirty propagation;
- authorized asset resolver port with preview/full tiers and version fingerprints;
- font resolver + text measurement port + font invalidation remeasure path;
- versioned style/brand-token resolution;
- signed URL exclusion from semantic scene hashing;
- per-node render fingerprints plus compact final SHA-256 scene hash;
- compiler/version/resource/font/token provenance payload and NODE-15 sink boundary;
- CompiledScene -> NODE-40 SceneSnapshot bridge;
- incremental renderer patch bindings and executable `CanvasCompilerRendererRuntime`;
- fixture snapshot, Vitest contract suite, static validator, benchmark harness, dedicated CI and production gap ledger.

## Local evidence

The exact NODE-41 candidate source was exercised in an isolated workspace:

```text
NODE41_TS_STRICT_COMPILE_PASS
NODE41_TS_TEST_SUITE_STRICT_COMPILE_PASS
NODE41_CANVAS_COMPILER_SMOKE_PASS
```

Local compiler: TypeScript 5.8.3 with repository-equivalent strict options. Node runtime: 22.16.0. Repository TypeScript 6.0.3, pnpm 11.4.0 and actual Vitest execution are not claimed locally.

Reference measurements after the compact render-fingerprint optimization:

```text
Full compile 2k:   ~143 ms
Full compile 10k:  ~453 ms
Incremental 2k single-node change:   ~54 ms; patch upserts=1
Incremental 10k single-node change: ~159 ms; patch upserts=1
```

These are isolated CPU reference measurements only. They are not browser/GPU/standard-hardware release SLO evidence.

## Correctness assertions exercised locally

- rotating authorized/signed URLs with unchanged resource versions keeps `sceneHash` stable;
- parent Frame geometry change expands dirty descendants and incremental result matches full result by `sceneHash`;
- font invalidation recompiles the dependent Text node without re-resolving unrelated image assets;
- compiler provenance sink receives `compiler_version=1.0.0`;
- compiled resource identity bridges into NODE-40 renderer snapshots;
- structural-invalid documents reject compile;
- missing render resources isolate to placeholders rather than failing the document.

## Production qualification

Five production gaps remain open and are not claimed complete:

1. production authorized asset/font/style resolver adapters;
2. durable NODE-15 Artifact provenance persistence adapter;
3. browser/export-server controlled font metric conformance;
4. pinned PixiJS v8 browser materialization inherited from NODE-40;
5. NODE-08 standard-hardware compiler performance calibration/gates.

See `reports/nodes/NODE-41/gap-ledger.json`.

## Hosted acceptance gate

An allocated runner must execute frozen pnpm install, repository TypeScript 6.0.3 package typecheck, the NODE-41 Vitest suite, static validator, fixture/gap validation, and lock reproducibility. Browser/font/Pixi gaps require separate real-browser evidence rather than inference from headless tests.

Next node: **NODE-42 — Artifact Engine**.
