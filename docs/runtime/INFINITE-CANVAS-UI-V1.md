# Infinite Canvas Product Runtime Contract V1

Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**

## 1. Source of truth

The Canvas DOM/SVG/Pixi/WebGL renderer is never persisted truth. Production truth remains Python Design IR stored as immutable `design_document_versions`; `design_documents.head_version_id` identifies the current editable checkpoint.

NODE-55 introduces a browser-only Canvas Projection that adapts canonical Python Design IR to the existing TypeScript NODE-40 Canvas SDK. Projection normalization is one-way: normalized renderer documents are never written back to PostgreSQL.

## 2. Cross-runtime projection

The API exposes:

```text
GET /api/v1/design-documents/{design_document_id}/canvas
GET /api/v1/artifact-versions/{artifact_version_id}/canvas
```

Each projection contains:

```text
design_document_id
design_document_version_id
version_number
revision
content_hash
active_page_id
document
```

The exact ArtifactVersion route resolves its exact `design_document_version_id`, not the mutable DesignDocument head.

Browser normalization currently maps:

```text
lumi.design-ir/1.0 -> 1.0
Python Page.parent_id=null -> synthetic DOCUMENT_ROOT parent in projection only
```

## 3. Command boundary

Browser interaction uses the existing `@lumi/canvas-sdk` generic operation descriptor contract. Descriptors are not stored or trusted as Python Design IR operations.

The API command endpoint is:

```text
POST /api/v1/design-documents/{design_document_id}/commands
```

Request fencing:

```text
client_batch_id
expected_design_document_version_id
expected_version_number
expected_revision
descriptors[]
```

The server locks the DesignDocument row, verifies the exact head/version/revision, explicitly compiles the safe descriptor allowlist into Python typed operations, calls `apply_batch`, writes one immutable DesignDocumentVersion and advances the head under the same transaction/CAS.

Unknown operations/properties fail closed. No arbitrary JSON patch path exists.

## 4. Idempotency

The browser uses the same UUID `client_batch_id` for the HTTP `Idempotency-Key` and the persisted Design IR metadata marker `canvas_last_client_batch_id`.

If a write committed but its HTTP response was lost, retrying the same batch against the new head returns that already-created canonical version rather than creating another checkpoint or reporting a false user conflict.

## 5. Request-scoped database lifetime

`PostgresCanvasDocumentService` owns a SQLAlchemy Session and therefore must never be an application singleton.

FastAPI requires `app.state.canvas_document_service_factory`, a context-manager factory that yields one service/Session per request and closes it afterward. Missing composition returns 503.

## 6. Autosave

Browser flow:

```text
Canvas SDK local operation preflight
→ committed-descriptor hook
→ bounded local command buffer (max 120)
→ 700 ms debounce / interaction-end
→ one command batch
→ server DesignDocumentVersion
→ canonical projection acknowledgement
```

Network/response-loss retries preserve the same active batch id/base. A 409 version conflict freezes further persistence and preserves queued commands until the user explicitly reloads canonical state. Offline mode retains the bounded in-memory queue and retries after reconnect.

NODE-55 does not persist unsaved command queues in localStorage/sessionStorage.

## 7. Interaction engine

NODE-55 reuses NODE-40 `CanvasController`, `CanvasCamera`, `SelectionModel`, spatial index and `TransformSession` rather than reimplementing them in React.

Current core product controls include:

- multiple Frame presets: 1:1, 4:5, 9:16, 16:9, A4;
- click and shift selection;
- drag move with renderer-local preview;
- Space/middle-button pan;
- cursor-centered wheel zoom;
- fit all;
- Delete/Backspace subtree delete;
- lock/unlock;
- bounded context menu;
- viewport culling and low-zoom renderer simplification inherited from NODE-40.

Remaining professional controls are tracked in the NODE-55 gap ledger rather than mocked.

## 8. Agent selection safety

NODE-54 accepts Canvas selection context only while Canvas state is `saved`:

```json
{
  "selected_node_ids": ["..."],
  "design_document_version": 17
}
```

When Canvas is `dirty`, `saving`, `offline`, `conflict`, or `error`, selection is removed from Agent context and a new Agent run is blocked until canonical save state is restored. This prevents AI edits against a local-only document revision.

## 9. CSRF / tenant scope

Browser business mutations use session cookies plus the `lumi_csrf` double-submit cookie as `X-CSRF-Token`. Canvas requests also send the server-validated organization id in `X-Organization-ID`.

## 10. Conflict semantics

A version mismatch never silently overwrites remote changes. Current P0 behavior is explicit conflict + user-triggered canonical reload. Semantic rebase/forking of historical versions is a later completion item.

## 11. Renderer boundary

The current product adapter is renderer-neutral SVG and consumes only `RendererFrame`. DOM/SVG handles never enter Design IR. The adapter can be replaced by Pixi/WebGL later without changing persistence or operation contracts.
