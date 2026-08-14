# LUMI Canvas Compiler Runtime V1

> NODE: 41 — Canvas Compiler  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Depends on: NODE-38 Design IR Runtime, NODE-39 Constraint Validator, NODE-40 Canvas Engine

## 1. Purpose

Canvas Compiler is the deterministic boundary between persisted Design IR and disposable renderer state.

```text
DesignDocument
→ Design IR validation
→ deterministic defaults / style tokens
→ geometry projection
→ resource + font resolution
→ text measurement
→ CompiledSceneSnapshot
→ CanvasRenderPlan
→ PixiV8RendererAdapter
```

The compiler does **not** create a second persisted design protocol. `CompiledSceneSnapshot`, resource URLs, font handles, measurements, render keys and Pixi objects are disposable runtime state.

## 2. Core invariants

1. Design IR remains the only persisted canvas source of truth.
2. Compiler output is reproducible from the same Design IR, compiler version and resource/font versions.
3. PixiJS is absent from compiler contracts and compiler core.
4. Presigned/expiring URLs may exist in resolved runtime resources but are excluded from deterministic compile hash.
5. `compiler_version` is explicit and travels in compile provenance.
6. A global structural invalidity rejects compilation.
7. A renderer-unsupported individual node becomes a placeholder with diagnostics.
8. Missing assets/fonts degrade to diagnostics/placeholders rather than mutating Design IR.
9. Incremental compile must converge to the same compile hash/render plan as a fresh full compile.
10. Schema/root/compiler-version changes may force an explicit full-compile fallback.

## 3. Runtime modules

```text
packages/canvas-sdk/src/
  compiler-types.ts
  compiler-resolvers.ts
  compiler-dirty.ts
  compiler-cache.ts
  compiler.ts
  compiler-benchmark.ts
```

The existing NODE-40 modules remain downstream:

```text
controller.ts
renderer.ts
pixi-v8-bindings.ts
asset-residency.ts
```

`CanvasController` now receives a `CanvasSceneCompilerPort`. The default implementation is `CanvasCompiler`, so production scene construction passes the compiler boundary before Canvas spatial indexing/rendering.

## 4. CompiledSceneNode

A compiled node extends the renderer-neutral Canvas scene node with only runtime render inputs:

```text
resolved_style
style_versions
resolved_text
resolved_resource
interaction_flags
clip_id / mask_id
placeholder
```

It still carries NODE-40 geometry:

```text
local_matrix
world_matrix
local_bounds
world_bounds
paint_order
visible / locked
```

No compiler field is written back to `DesignDocument`.

## 5. Full compile

`CanvasCompiler.fullCompile(document)` performs:

1. NODE-38 `validateDocument()`;
2. reject fatal graph/schema/root failures;
3. project deterministic nested geometry;
4. resolve style tokens and their versions;
5. resolve asset reference through `CompilerAssetResolver`;
6. resolve font through `CompilerFontResolver`;
7. measure text through `CompilerTextMeasurer`;
8. emit render plan;
9. collect resource/font versions;
10. calculate canonical SHA-256 `compile_hash`.

The default full compile does not use cache. Cache must be opted into explicitly.

## 6. Structural compile for interactive Canvas

High-frequency Canvas interactions do not wait for network resources. `compileStructure()` performs the synchronous deterministic part and emits pending asset references.

NODE-40 uses this path after authoritative Design Operations commit:

```text
Design Operation
→ NODE-39 guardedExecute
→ authoritative DesignDocument
→ CanvasCompiler.compileStructure
→ spatial index / selection / renderer
```

Async GPU residency stays in NODE-40 `CanvasAssetResidency`.

This separation keeps pointer interaction responsive while retaining one canonical compile model.

## 7. Incremental compile

`incrementalCompile()` receives:

```text
previous compiled snapshot
before DesignDocument
after DesignDocument
optional NODE-38 SemanticDiff
```

Dirty planning expands changes by dependency:

```text
changed node
+ descendants for geometry/inherited state
+ ancestors for order/structural changes
+ resource/style/font dependents
+ removed-node former parent
```

Resource table changes are detected independently from NODE-38 `semanticDiff`, because semantic diff intentionally focuses on node/schema/provenance semantics.

### Full fallback

Incremental compile intentionally falls back to full compile when:

- Design IR schema version changes;
- root changes;
- compiler version changes.

Fallback is reported using `INCREMENTAL_FALLBACK` rather than silently pretending an incremental result was produced.

## 8. Resource resolution

Interfaces:

```text
CompilerAssetResolver
CompilerFontResolver
CompilerStyleResolver
CompilerTextMeasurer
```

Production can inject authorization-aware resolvers. Default document resolvers are deterministic/offline fallbacks for fixtures and local operation.

Runtime asset resolution returns:

```text
asset_id
variant
version
status
fingerprint
uri?          # runtime only
mime_type?
width?
height?
```

Missing resource:

```text
status = MISSING
+ RESOURCE_MISSING diagnostic
+ renderer remains able to show placeholder
```

## 9. Font contract

Font resolution is keyed by stable font ref/resource identity rather than browser-local font family alone.

Resolved font contains:

```text
font_ref
family
version
status
style?
weight?
uri?          # runtime only
fingerprint
```

Default `DeterministicTextMeasurer` exists for tests/offline determinism. Export production may replace it with the controlled server font-shaping stack while preserving the same compiler interface.

When a font resource version changes, dirty planning marks dependent Text nodes for recompile/remeasure.

## 10. Style tokens

`style_refs` are resolved in declared order. Later style refs override earlier properties.

Each compiled node records:

```text
resolved_style
style_versions
```

Direct visual properties currently normalized into compiled style include:

```text
opacity
blend_mode
```

Style resource versions are included in compile provenance alongside image/video assets.

## 11. Masks and clipping

Compiler reads renderer-neutral `mask_id` / `clip_id` references from node metadata and places them into compiled node/render plan.

`PixiV8RendererAdapter` performs a second materialization pass after display creation and binds the referenced mask handle. The compiler remains Pixi-free.

## 12. Deterministic hash

`compile_hash` is canonical SHA-256 over deterministic render semantics:

```text
compiler_version
document/schema/root identity
paint order
matrices/bounds
resolved style + style versions
resolved text + font version + measured metrics
resolved asset identity + version + dimensions
interaction flags
clip/mask ids
placeholder state
```

It deliberately excludes:

```text
presigned URI
font presigned URI
GPU handle
Pixi object identity
wall-clock timestamps
selection/camera state
```

Therefore rotating a signed URL while preserving the same stable resource version does not change compile hash.

## 13. Compile provenance

Full compiler output includes:

```text
compiler_version
document_id
schema_version
document_version
resource_versions
font_versions
compile_hash
```

This object is the direct provenance handoff for NODE-42 Artifact Engine.

## 14. Cache

`CanvasCompilerCache` is a bounded LRU cache.

`canvasCompilerCacheKey()` uses canonical Design IR plus compiler version. Full compile caching is opt-in; callers using external resolvers whose stable version can change independently from Design IR must avoid stale cache reuse or provide an invalidation policy at the integration layer.

No cache entry becomes persisted document state.

## 15. Error policy

### Fatal

Compilation rejects when the document has:

```text
IR graph cycle
unsupported schema major
missing root reference
missing document identity
```

### Recoverable

Recoverable conditions produce diagnostics and continue where safe:

```text
missing style token
missing asset
missing font
asset/font resolver error
text measurement error
renderer-unsupported custom node
non-fatal graph/reference diagnostic
```

## 16. Pixi bridge

NODE-41 extends the NODE-40 renderer bridge so compiled values are materialized rather than ignored:

- shape fill prefers `resolved_style`;
- Text gets compiled fill/font size/family/weight/line height/alignment;
- opacity/blend mode use normalized compiled style;
- `mask_id`/`clip_id` bind through renderer-neutral `setMask()`;
- Pixi runtime types remain isolated to bindings.

## 17. Tests

Primary suites:

```text
compiler.test.ts
compiler-renderer.test.ts
compiler-benchmark.test.ts
```

Coverage includes:

- deterministic hash;
- signed URI exclusion;
- compiler version provenance;
- asset/style/font version provenance;
- missing resource placeholder;
- custom-node placeholder;
- graph-cycle rejection;
- full/incremental equivalence;
- resource-only dirty invalidation;
- compiler-version full fallback;
- authorized async resolver injection;
- bounded cache;
- production CanvasController compiler routing;
- compiled style/mask Pixi bridge;
- 2k node / 100 operation benchmark equivalence.

## 18. Benchmark policy

NODE-41 benchmark is primarily a correctness/scalability harness:

```text
2,000 logical nodes
100 Design Operations
full compile
incremental compile
compile-hash equality
partial dirty/upsert set
```

No absolute latency is claimed until the hosted runner actually executes. Representative hardware browser/GPU performance remains NODE-69 responsibility.

## 19. Artifact handoff

NODE-42 should consume:

```text
CompiledSceneSnapshot.render_plan
CompiledSceneSnapshot.provenance
```

Artifact Engine must not reconstruct visual semantics directly from Pixi objects or browser state.

## 20. Completion rule

NODE-41 is **not COMPLETE** until hosted CI actually executes green for:

```text
compiler contract validator
Canvas SDK typecheck/tests
incremental/full equivalence tests
compiler benchmark harness
web Canvas integration typecheck
```

If GitHub Actions cannot start because of the known account billing/spending-limit condition, record the condition as an external CI blocker and keep the node at **IMPLEMENTED / VALIDATING / not COMPLETE**.
