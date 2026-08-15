# NODE-55 Acceptance Evidence

> Node: Infinite Canvas UI  
> Status: IMPLEMENTED / VALIDATING / NOT COMPLETE  
> Base: `node-54-ai-workspace-release` @ `ecc1f5f2dc995305ca605410e2f6307d0227e771`

## Implemented product surface

- NODE-54 center Canvas preview replaced by `InfiniteCanvasProduct`.
- Existing `CanvasController` is instantiated by the product route.
- Design IR remains the data truth source.
- Multi-frame initial world: 1:1, 4:5, 9:16.
- Frame presets include 1:1, 4:5, 9:16, 16:9 and A4.
- Pan, wheel zoom, zoom step, fit-all, fit-selection and frame navigation.
- CanvasSelectionModel selection flows into Agent context.
- Pointer drag uses CanvasTransformSession and commits DesignOperations on interaction end.
- READY Asset and exact ArtifactVersion drag payloads.
- Copy/paste/duplicate/delete, lock/unlock and arrange commands.
- Semantic undo/redo using Design IR inverse operations.
- In-memory autosave batching with server-base-version rebasing.
- Offline sync state and before-unload pending-command guard.
- Explicit Document version conflict state with Rebase and Reload.
- AI Send blocked unless Canvas sync state is SAVED.
- Viewport culling and low-zoom simplification.
- 2,000-node culling unit fixture.

## Reused lower-layer runtime

The implementation does not introduce a second scene graph. It directly reuses:

```text
@lumi/canvas-sdk
@lumi/design-ir
CanvasController
CanvasTransformSession
CanvasCompiler scene projection
DesignOperation executor
invertOperations
```

`apps/web/tsconfig.json` already mapped `@lumi/canvas-sdk` to the workspace source. NODE-55 adds the matching Design IR alias without changing package.json or pnpm-lock, preserving frozen-lockfile consistency.

## Autosave semantics

Local interaction transactions may advance local versions independently while server save is debounced. The autosave buffer rebases all pending operations to the canonical server base version before one atomic transaction.

Example:

```text
server v7
local interaction A -> local v8
local interaction B -> local v9
save A+B against expected server v7
server applies both operations atomically -> server v8
```

This matches the Design IR executor's transaction semantics and avoids submitting impossible mixed operation versions.

## Conflict evidence staged

The deterministic `project-canvas-conflict` fixture performs a canonical external edit before the first save. Expected UI flow:

```text
DIRTY
→ save expected old version
→ DOCUMENT_VERSION_CONFLICT
→ CONFLICT
→ Rebase local commands
→ fetch canonical
→ replay local commands at canonical version
→ save
→ SAVED
```

A separate Reload canonical path discards the local buffer/history deliberately.

## Unit coverage staged

- autosave rebase across multiple local versions;
- prefix-only acknowledgement while a save is in flight;
- nested BATCH version rehydration;
- one atomic save increments canonical version once;
- deterministic external edit creates conflict;
- mixed operation versions are rejected;
- 2k-node viewport culling;
- selected offscreen nodes remain render candidates.

## Browser coverage staged

- 3 initial frames on one infinite world;
- create 16:9 frame and autosave;
- Canvas selection becomes AI Edit context;
- READY Asset drag/drop creates IMAGE node and persists;
- locked node context menu disables Delete;
- explicit conflict Rebase path;
- focused mobile Canvas tab.

NODE-54 AI Workspace browser scenarios are rerun as regression coverage.

## Static validation definition

```text
python scripts/validate_infinite_canvas.py
```

The validator checks:

- Canvas SDK + Design IR aliases;
- server-selected Canvas bootstrap;
- CanvasController / transform-session reuse;
- multi-frame presets;
- pan/zoom/fit;
- Asset and Artifact drag contracts;
- DesignOperation autosave buffer;
- version rebase semantics;
- explicit conflict recovery;
- Agent Send saved-state gate;
- exact selection context;
- viewport culling + 2k test;
- production E2E guard;
- no durable browser canonical state.

## Hosted gate definition

`.github/workflows/infinite-canvas.yml` defines:

```text
infinite-canvas-contract
infinite-canvas-quality
infinite-canvas-build
infinite-canvas-browser-e2e
```

The workflow uses Node 24 / pnpm 11.4.0 and the repository's pinned TypeScript 6.0.3 toolchain.

## Completion blockers

NODE-55 cannot be marked COMPLETE until:

1. hosted typecheck/lint/unit/build/Playwright gates actually execute green;
2. the canonical production Canvas operations API is connected or formally superseded;
3. production route renderer/Pixi parity and performance are validated.

GitHub Actions on NODE-53/NODE-54 were already observed failing before runner start because of account payment/spending-limit state. If NODE-55 receives the same platform annotation, that must be recorded as a hosted execution blocker rather than a code/test failure.

## Current verdict

```text
Infinite Canvas product surface   IMPLEMENTED
CanvasController integration      IMPLEMENTED
autosave batching                 IMPLEMENTED
version conflict recovery         IMPLEMENTED
Asset / Artifact drag contracts   IMPLEMENTED
AI exact-selection integration    IMPLEMENTED
2k viewport culling coverage      IMPLEMENTED
static architecture gate          READY TO EXECUTE ON COMMITTED TREE
pinned hosted gates               PENDING
canonical save backend            UPSTREAM DEPENDENCY
production renderer parity        VALIDATION DEPENDENCY
```

NODE-55 is **IMPLEMENTED / VALIDATING / NOT COMPLETE**.
