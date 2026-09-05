# NODE-41 — Canvas Compiler Acceptance

> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Branch: `node-41-canvas-compiler`  
> Base: `node-40-canvas-engine-release`

## Scope evidence

| Requirement | Evidence | State |
| --- | --- | --- |
| Design IR remains source of truth | `compiler.ts`, `controller.ts` | IMPLEMENTED |
| No second persisted canvas protocol | compiled scene/render plan are disposable | IMPLEMENTED |
| Renderer-neutral compiler | compiler modules contain no Pixi dependency | IMPLEMENTED |
| Full compile | `CanvasCompiler.fullCompile()` | IMPLEMENTED |
| Interactive structural compile | `CanvasCompiler.compileStructure()` | IMPLEMENTED |
| Incremental compile | `CanvasCompiler.incrementalCompile()` | IMPLEMENTED |
| Dirty dependency expansion | `compiler-dirty.ts` | IMPLEMENTED |
| Resource-only invalidation | independent resource-table diff | IMPLEMENTED |
| Structural full fallback | schema/root/compiler version fallback | IMPLEMENTED |
| Deterministic compile SHA-256 | `compile_hash` | IMPLEMENTED |
| Compiler version provenance | `CANVAS_COMPILER_VERSION`, provenance | IMPLEMENTED |
| Asset version provenance | `resource_versions` | IMPLEMENTED |
| Style token version provenance | per-node `style_versions` + `resource_versions` | IMPLEMENTED |
| Font version provenance | `font_versions` | IMPLEMENTED |
| Signed URI excluded from compile hash | `hashableResource` / `hashableFont` | IMPLEMENTED |
| Authorized asset resolver contract | `CompilerAssetResolver` | IMPLEMENTED |
| Font resolver contract | `CompilerFontResolver` | IMPLEMENTED |
| Style resolver contract | `CompilerStyleResolver` | IMPLEMENTED |
| Text measurement contract | `CompilerTextMeasurer` | IMPLEMENTED |
| Missing asset placeholder | `RESOURCE_MISSING` + MISSING resource | IMPLEMENTED |
| Missing font diagnostic | `FONT_MISSING` | IMPLEMENTED |
| Custom node placeholder | `NODE_PLACEHOLDER` | IMPLEMENTED |
| Global cycle rejection | NODE-38 validation gate | IMPLEMENTED |
| Compiled style to Pixi | renderer + `pixi-v8-bindings.ts` | IMPLEMENTED |
| Compiled Text style/font to Pixi | text style bridge | IMPLEMENTED |
| Mask/clip bridge | renderer second pass + `setMask` | IMPLEMENTED |
| Missing mask handle retry | renderer records only actually bound mask handle | IMPLEMENTED |
| CanvasController uses compiler | injected `CanvasSceneCompilerPort` | IMPLEMENTED |
| Compile LRU cache | `compiler-cache.ts` | IMPLEMENTED |
| Full/incremental equivalence test | `compiler.test.ts` | IMPLEMENTED; hosted execution blocked |
| Compiler/Pixi bridge test | `compiler-renderer.test.ts` | IMPLEMENTED; hosted execution blocked |
| 2k/100-op benchmark | `compiler-benchmark.ts` | IMPLEMENTED; hosted execution blocked |
| Architecture validator | `scripts/validate_canvas_compiler.py` | IMPLEMENTED; hosted execution blocked |
| Runtime documentation | `docs/runtime/CANVAS-COMPILER-V1.md` | IMPLEMENTED |
| Dedicated CI | `.github/workflows/canvas-compiler.yml` | IMPLEMENTED; hosted runner blocked |

## Compiler boundary

Persisted:

```text
DesignDocument
DesignOperation
Constraint
stable resource/version identity
```

Disposable:

```text
CompiledSceneSnapshot
CanvasRenderPlan
resolved runtime URI
resolved font runtime data
text measurements
compile cache
Pixi materialization
```

No resolved URL, font handle, compile patch, render plan, Pixi object or cache state is written into Design IR.

## Full compile acceptance

```text
DesignDocument
→ NODE-38 validateDocument
→ NODE-40 geometry projection
→ style token normalization
→ asset/font resolution
→ text measurement
→ render plan
→ canonical SHA-256
→ compile provenance
```

Fatal root/schema/cycle errors reject compile. Node-local renderer unsupported kinds remain placeholders with diagnostics.

## Incremental acceptance

Dirty planning includes:

```text
changed nodes
+ inherited descendants
+ structural/order ancestors
+ removed-node former parent
+ changed asset dependents
+ changed style token dependents
+ changed font dependents
```

Resource-table changes are checked even when NODE-38 `semanticDiff.changed` is false.

Incremental output includes:

```text
removed_node_ids
upserted_nodes
paint_order
dirty_node_ids
fallback_to_full
```

A correctness test compares incremental `compile_hash` and `render_plan` against a fresh full compile.

## Provenance acceptance

Full compile provenance contains:

```text
compiler_version
document_id
schema_version
document_version
resource_versions  # asset + style token
font_versions
compile_hash
```

The compile hash excludes expiring asset/font URIs. A regression test compiles two documents differing only in signed asset URL token and expects identical `compile_hash` while resource version is unchanged.

## Pixi acceptance

NODE-41 does not move Pixi into compiler core. The existing NODE-40 adapter consumes compiled nodes and materializes:

- resolved shape fill;
- resolved text fill/font/size/weight/line-height/alignment;
- opacity/blend mode;
- mask/clip references.

If a referenced mask display is not materialized, the adapter does not mark the mask id as successfully bound. A later sync can therefore retry when the display becomes available.

`PixiV8RendererAdapter` remains replaceable by another renderer using the same `CanvasRenderPlan` / compiled scene semantics.

## Benchmark acceptance

Harness:

```text
2,000 total nodes
100 MOVE_NODE operations
fresh full compile after operations
incremental compile from previous compiled snapshot
```

Pass conditions encoded in test:

- no full fallback for the normal 100-operation case;
- incremental and full compile hashes equal;
- dirty/upsert set is smaller than total scene;
- benchmark reports finite timing values.

No absolute latency claim is made until hosted execution produces evidence.

## Tests present

- `compiler.test.ts`
  - deterministic full compile;
  - signed URL exclusion;
  - complete version provenance;
  - missing asset;
  - graph cycle;
  - custom placeholder;
  - full/incremental equality;
  - resource-only invalidation;
  - compiler-version fallback;
  - custom authorized resolvers;
  - cache;
  - CanvasController compiler routing.
- `compiler-renderer.test.ts`
  - resolved style bridge;
  - mask bridge.
- `compiler-benchmark.test.ts`
  - 2k node / 100 operation equivalence harness.

## Hosted CI evidence

Initial release head:

```text
38716eebe756f74a6f3258fd278d6f2f5d02d90e
```

Canvas Compiler workflow run:

```text
31787967035
```

Observed jobs:

```text
compiler-contract      failure before any step executed
compiler-quality       skipped
compiler-equivalence   skipped
compiler-benchmark     skipped
```

GitHub check annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings

Therefore no NODE-41 architecture validator, dependency-complete TypeScript typecheck, unit/conformance test or benchmark step executed in hosted CI. This is an external GitHub Actions account/billing blocker, not an observed compiler code/test failure.

The local execution environment contains `tsc`, but cannot resolve `github.com`, so it cannot clone the real workspace and pinned dependencies. No dependency-complete local PASS is claimed either.

## Acceptance gates before COMPLETE

1. Hosted compiler architecture validator executes green.
2. Hosted Canvas SDK TypeScript typecheck executes green.
3. Hosted Canvas SDK unit/conformance tests execute green.
4. Hosted web typecheck proves real `/canvas-engine` remains compatible.
5. Hosted 2k/100-op benchmark executes and records results.
6. Full/incremental hash equivalence stays green.
7. No Design IR / Constraint contract drift.
8. Release PR remains stacked on `node-40-canvas-engine-release`.

## Current disposition

Implementation, compiler contracts, full/incremental execution, deterministic hashing, resource/font/style resolution, Canvas/Pixi integration, tests, benchmark harness, architecture validator, runtime documentation and dedicated CI are present.

NODE-41 remains **IMPLEMENTED / VALIDATING / not COMPLETE**. Hosted execution is currently blocked by the GitHub Actions billing/spending-limit condition. The blocker is recorded as external CI infrastructure evidence and is not treated as code PASS or code failure.
