# NODE-55 — Infinite Canvas Implementation

Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**  
Branch: `feat/node-55-infinite-canvas-ui`  
Stack base: `feat/node-54-ai-workspace`

## Implemented architecture

```text
exact ArtifactVersion / DesignDocument head
→ tenant-scoped Canvas Projection API
→ one-way Python Design IR → TS Canvas projection normalization
→ existing NODE-40 CanvasController/Selection/Camera/TransformSession
→ renderer-neutral SVG product adapter
→ local committed-descriptor hook
→ bounded autosave buffer
→ exact head/version/revision fenced command API
→ browser descriptor → Python typed operation compiler
→ Python apply_batch
→ immutable DesignDocumentVersion
→ canonical head CAS
→ acknowledged projection
```

## Persistence and concurrency

- Canvas never persists DOM/SVG/renderer state.
- Every write locks the DesignDocument row with `FOR UPDATE`.
- `expected_design_document_version_id`, version number and Design IR revision must all match.
- One command batch creates exactly one immutable DesignDocumentVersion.
- Head advancement is inside the same transaction and expected-head fenced.
- 409 conflict never silently overwrites another editor/agent write.
- `client_batch_id` is persisted as `canvas_last_client_batch_id`; retry after a lost HTTP response can identify its already-committed result.
- API dependency requires a request-scoped service factory; a SQLAlchemy Session is never designed as a shared app singleton.

## Cross-runtime compiler

The browser uses the existing generic NODE-40 operation descriptor. The server explicitly compiles an allowlist to production Python Design IR operations.

Currently supported:

```text
CREATE_NODE (FRAME only)
MOVE_NODE (absolute x/y)
RESIZE_NODE
ROTATE_NODE
DELETE_NODE (recursive subtree semantics)
SET_TEXT
REPLACE_ASSET
SET_PROPERTY: locked / visible / opacity / name
```

Unknown operations/properties are rejected; no arbitrary JSON patch is exposed.

## Product interaction implemented

- multi-Frame infinite surface;
- 1:1 / 4:5 / 9:16 / 16:9 / A4 Frame presets;
- click/shift selection;
- drag move with `TransformSession` local preview;
- Space/middle pan;
- wheel zoom to cursor;
- Fit All;
- Delete/Backspace;
- lock/unlock and bounded context menu;
- save/offline/conflict status UI;
- explicit canonical reload after conflict;
- bounded in-memory autosave queue + beforeunload warning;
- viewport culling and low-zoom simplification through NODE-40 engine;
- exact ArtifactVersion Canvas load;
- saved-only selection handoff to NODE-54 Agent composer.

## Security and request correctness

NODE-55 also closes a real browser-auth integration gap found while wiring mutations: unsafe browser API requests now copy the readable `lumi_csrf` double-submit cookie into `X-CSRF-Token`, while tenant business requests continue to carry the server-validated organization id.

## Tests added

- Canvas SDK committed-descriptor hook emits only successful local operations;
- browser projection normalizes Python schema/page roots without mutating server truth;
- browser generic CREATE/SET_PROPERTY/DELETE descriptors compile to the safe wire;
- Python projection contains no renderer handles;
- MOVE semantics are absolute and RESIZE maps to typed Python operations;
- CREATE_FRAME requires UUIDv7 and explicit geometry;
- static validator locks request-scoped DB service, exact-version fencing, same-batch replay, CSRF, bounded autosave, conflict freeze, SDK reuse, and saved-only Agent selection.

## Explicitly not complete

The remaining P0/P1 work is listed in `reports/nodes/NODE-55/gap-ledger.json`. In particular, this branch does not claim complete Asset/file drag-drop, full professional transform/arrange/copy-group controls, deployed DB composition, autosave concurrency E2E, 2k-node browser performance acceptance, or Hosted CI execution if the runner never starts.
