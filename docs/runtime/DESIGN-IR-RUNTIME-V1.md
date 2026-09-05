# Design IR Runtime V1

> Node: NODE-38  
> Contract sources: NODE-13 Design IR, NODE-14 Constraint Engine, NODE-15 Artifact Version & Provenance  
> Runtime status: IMPLEMENTED / VALIDATING

## 1. Boundary

Design IR Runtime is the only supported mutation boundary for persisted Design IR snapshots. Agents, Canvas, exporters and server-side workers must submit structured Design Operations instead of mutating persisted JSON directly.

NODE-38 performs structural validation and exposes a constraint preflight boundary; the actual hard/soft constraint rules remain owned by NODE-39.

## 2. Runtime surfaces

TypeScript (`packages/design-ir`) provides:

- `parseDocument` / `validateDocument`
- `executeOperation` / `executeOperations`
- `canonicalStringify` / `canonicalDocument` / `hashDocument`
- `semanticDiff`
- `DesignIrMigrationRegistry`
- `queryNodes`
- `boundsFromTransform` / `buildSpatialEntries` / `SpatialIndexAdapter`
- `DesignIrHistory`

Python (`services/domain/src/lumi_domain`) provides the server/Agent mirror:

- `design_ir_runtime.py`: atomic operation executor, canonical primitive helpers, semantic diff and migration registry
- `design_ir_canonical.py`: NFC canonical document/hash policy and ephemeral metadata exclusion
- `design_ir_document.py`: parser, graph/reference validation, selectors and spatial entries

## 3. Transaction semantics

A call to `executeOperations(document, operations)` is one document transaction:

1. Read `metadata.document_version` (missing means version `0`).
2. Clone the caller-owned snapshot.
3. Verify every operation expects the transaction's starting version.
4. Reject non-finite numeric payloads.
5. Apply operations only to the working copy.
6. If any operation fails, discard the working copy and return the exact original document with structured failure data.
7. On success, advance `metadata.document_version` exactly once.

A `BATCH` is recursively executed inside the same transaction and therefore cannot create a partial persisted version.

## 4. Operation contract

The NODE-13 V1 operation set is frozen in `packages/design-ir/src/types.ts`:

`CREATE_NODE`, `DELETE_NODE`, `SET_PROPERTY`, `MOVE_NODE`, `RESIZE_NODE`, `ROTATE_NODE`, `REORDER_NODE`, `REPARENT_NODE`, `REPLACE_ASSET`, `SET_TEXT`, `APPLY_STYLE`, `BATCH`.

The runtime protects root mutations, missing targets/parents, reparent cycles, optimistic version conflicts and non-finite values. NODE-39 will add hard/soft constraint outcomes without changing this operation protocol.

## 5. Structural validation

Validation checks:

- Design IR major version support;
- root reference existence;
- node map key ↔ `node.id` identity;
- V1 node kind compatibility;
- parent and child references;
- parent/child back-reference consistency;
- graph cycles;
- finite numeric values.

Errors carry a machine code plus JSON-pointer-like location and, when available, a node id.

## 6. Canonical hash policy

Document hashes use SHA-256 over deterministic UTF-8 JSON with:

- lexicographically stable object keys;
- preserved array order;
- NFC Unicode normalization;
- `-0` normalized to `0`;
- NaN and Infinity rejected;
- ephemeral metadata excluded (`updated_at`, `last_accessed_at`, `selection`, `viewport`, `cursor`, `ephemeral:*`, `_ephemeral*`);
- stable persisted resource ids left intact.

`fixtures/design-ir/node-38-conformance.json` freezes input/output hash vectors used by both runtimes.

## 7. Semantic diff

The TypeScript runtime classifies changes as node add/remove, geometry, text, asset, constraint, order, generic property, provenance and schema-version changes. This is the contract consumed later by Versions UI, Critic and audit surfaces.

## 8. Semantic query and spatial hook

`queryNodes` supports id, role, kind, parent, brand binding, asset binding and locked-state selectors so Agent tools can request a local semantic slice instead of sending an entire document into model context.

Spatial indexes are adapters only. `buildSpatialEntries` derives transient bounds from Design IR; RBush or Canvas-specific indexes must never be persisted into IR.

## 9. Migration

Migrations are explicit one-hop pure functions registered as `from -> to`. The registry refuses missing paths and cycles and restores provenance if a migration accidentally omits it. No implicit major-version guessing is allowed.

## 10. History

`DesignIrHistory` records immutable before/after snapshots and operation lists and offers deterministic undo/redo for editor command history. Persisted version history remains an Artifact/Version concern rather than a browser history object.

## 11. Conformance and quality gates

Shared fixture/tests cover:

- TS/Python input and output hash vectors;
- deterministic repeated execution;
- immutable caller snapshots;
- atomic rollback;
- version conflicts;
- semantic text/geometry diff;
- migration provenance preservation;
- parser/cycle validation;
- selector behavior;
- Unicode + ephemeral metadata hash policy;
- undo/redo behavior.

`.github/workflows/design-ir-runtime.yml` gates contract/typecheck, Python quality and a 2,000-node / 100-operation benchmark. The benchmark budget is 1,500 ms median on the hosted baseline and is intentionally isolated from functional correctness.

## 12. Integration rule for NODE-39+

All downstream code must call this runtime rather than editing persisted `nodes`, `resources` or `metadata` in place. NODE-39 may reject a candidate through constraint preflight, but it must not fork a second Design IR mutation implementation.
