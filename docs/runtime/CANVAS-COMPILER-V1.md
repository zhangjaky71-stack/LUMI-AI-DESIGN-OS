# LUMI Canvas Compiler V1 — NODE-41

## Status

`IMPLEMENTED / VALIDATING`

NODE-41 establishes the stable compilation boundary between NODE-38 Design IR and NODE-40 Canvas rendering.

```text
Design IR
  -> NODE-38 structural validation
  -> compiler normalization
  -> style/token resolution
  -> asset/font authorization resolution
  -> deterministic geometry/world transform compilation
  -> CompiledSceneNode
  -> incremental scene patch
  -> NODE-40 renderer-neutral adapter
  -> PixiJS v8 materialization boundary
```

The compiler never persists renderer objects and never writes resolved/signed URLs back into Design IR.

## Public runtime

Primary exports:

```ts
CanvasCompiler
CanvasCompilerRendererRuntime
compiledSceneToCanvasScene
applyCompiledPatch
CANVAS_COMPILER_VERSION
```

Core APIs:

```ts
compiler.compileFull(document)
compiler.compileIncremental({ previous, before, after, diff? })
compiler.compileResourceInvalidation(previous, document, invalidation)
compiler.recordProvenance(snapshot, sink)
```

## CompiledSceneNode

A compiled node contains rendering-only state:

```text
id / kind / parent / children
localTransform / worldTransform
localBounds / worldBounds
clipId / maskId
resolvedStyle + styleVersions
resolvedText + font version + measured metrics
resolvedResource + resource version + authorized runtime URL
zOrder
interactionFlags
visible / locked / opacity
placeholder + diagnostic codes
sourceFingerprint / renderFingerprint
```

This representation is ephemeral. It is not Design IR and must not be persisted as the design source of truth.

## Structural failure boundary

Before any scene compilation, NODE-41 calls NODE-38 `validateDocument`.

A structurally invalid graph such as a missing child, parent mismatch, graph cycle, unsupported schema, or unreachable node rejects the whole compile. A valid document containing one render-time problem does not crash the scene: the affected node produces diagnostics and a placeholder/fallback representation.

## Geometry and layout normalization

V1 implements deterministic hierarchical transform composition for Frame/Group/basic nodes. Local translation, scale, and rotation compile into a renderer-neutral 2D matrix. World bounds are the axis-aligned bounds of the transformed local rectangle.

This is intentionally not a hidden Pixi layout system. Advanced Auto Layout is not introduced as renderer convenience state; future deterministic layout rules must be represented in Design IR/compiler rules.

## Style / brand token resolution

`StyleCompileResolver` resolves ordered `style_refs`. The default document resolver consumes versioned entries from `DesignDocument.resources` and merges them deterministically; inline style values then override the resolved style.

Every resolved style/token records its version in `styleVersions`. Missing refs produce `COMPILER_STYLE_TOKEN_MISSING` without crashing unrelated nodes.

NODE-41 separately checks resource-table changes because NODE-38 `SemanticDiff` is node-oriented and resource changes can otherwise be invisible to incremental compilation.

## Asset resources

`AssetCompileResolver` receives:

```text
document
assetId
preview/full tier
nodeId
```

It returns an authorized runtime resource containing resource version/fingerprint and optionally a signed URL. The compiler validates resolver identity/tier and records version/fingerprint into the compiled node.

A signed URL is runtime-only. It is excluded from the deterministic scene hash and is never copied into Design IR.

Missing/failed IMAGE or VIDEO resources degrade that node to a placeholder with a diagnostic.

## Fonts and text

`FontCompileResolver` maps `font_ref` / `font_asset_id` to a versioned authorized font resource. `TextCompileMeasurer` then measures normalized NFC content.

The built-in `DeterministicTextMeasurer` is a headless fallback for tests/server-neutral behavior; it is not claimed to replace production browser/export font metrics.

When a font finishes loading or changes version:

```ts
compiler.compileResourceInvalidation(snapshot, document, {
  fontRefs: ["font-main"]
})
```

Only dependent TEXT nodes are re-resolved/re-measured and emitted in the incremental patch.

## Full compile

Full compile is used for initial open, schema migration, renderer recovery, and export snapshots. It traverses root child order deterministically, resolves all nodes, computes scene/provenance fingerprints, and returns compile diagnostics.

## Incremental compile

Dirty seeds come from NODE-38 `SemanticDiff`:

```text
nodes_added
nodes_removed
properties_changed
text_changed
geometry_changed
asset_replaced
constraints_changed
```

Dirty expansion includes relevant ancestors/descendants, group/frame transform descendants, mask/clip dependents, and resource-table dependents.

The compiler always recomputes the lightweight structural traversal/paint order, but expensive async resource/font/style/text compilation is performed only for dirty nodes. Unchanged nodes reuse their compiled representation and render fingerprint. Nodes whose only z-order changes are shallow-updated and included in the patch.

The result is:

```text
removedNodeIds
upsertedNodes
orderedIds
sceneHash
diagnostics
```

## Resource invalidation compile

External resource events are independent of Design IR operations. NODE-41 supports explicit invalidation for:

```text
assetIds
fontRefs
styleRefs
```

Only dependents are recompiled. This is the path used for async font completion, high-resolution asset version changes, and brand/style token refresh.

## Deterministic preview

Determinism is defined semantically:

```text
same Design IR
+ same compiler version
+ same resource/font/token versions and fingerprints
= same sceneHash
```

Presigned URL rotation does not affect `sceneHash` because authorization URLs are not semantic resource identity.

Each compiled node carries a short deterministic render fingerprint. The final scene SHA-256 is computed over compiler version, document identity, paint order, and the ordered render-fingerprint list. This allows unchanged node fingerprints to be reused during incremental compile instead of canonicalizing every full SceneNode again.

## Compiler provenance

Every successful compile contains:

```text
compiler_version
document_id
schema_version
document_hash
scene_hash
resource_versions
font_versions
token_versions
```

`recordProvenance(snapshot, sink)` is the NODE-15 integration boundary. Durable Artifact/Version persistence is intentionally a separate production adapter and remains recorded in the gap ledger.

## Renderer bridge

`compiledSceneToCanvasScene` converts CompiledScene into NODE-40 `SceneSnapshot` / `RenderNodeSnapshot` without exposing compiler internals to the renderer.

`applyCompiledPatch` maps incremental compiler patches to `CompiledRendererPatchBindings`:

```text
upsertNode
removeNode
setPaintOrder
```

`CanvasCompilerRendererRuntime` provides an executable full/incremental/resource-invalidation pipeline that owns the previous document/snapshot and applies patches to renderer bindings. A Pixi implementation can materialize this interface without changing Design IR or compiler code.

## Local reference measurements

Observed in the isolated implementation container using locally available TypeScript 5.8.3 and Node 22.16.0:

```text
Full compile 2k:   ~143 ms reference
Full compile 10k:  ~453 ms reference
Incremental 2k single-node change:   ~54 ms, 1 upsert
Incremental 10k single-node change: ~159 ms, 1 upsert
```

These are diagnostic CPU measurements, not release SLOs, browser frame times, GPU metrics, or NODE-08 standard-hardware results.

## Invariants

1. Design IR does not import or persist Pixi objects.
2. Compiler output is ephemeral and renderer-neutral.
3. Signed resource URLs never mutate Design IR and do not influence deterministic scene identity.
4. Structural-invalid documents fail globally; render-time node failures isolate locally.
5. Incremental compilation must produce the same semantic scene hash as full compile for the same final inputs.
6. Font/resource invalidation recompiles dependents only.
7. Compiler-version changes force full compile rather than mixing snapshots from different visual semantics.
8. Compiler version and resource versions are always available to Artifact provenance.

## Open production gaps

See `reports/nodes/NODE-41/gap-ledger.json`. NODE-41 does not claim production Asset Service adapters, durable NODE-15 provenance persistence, real cross-browser/export font metric parity, pinned PixiJS browser execution, or calibrated standard-hardware compiler performance.

## Next node

**NODE-42 — Artifact Engine.**
