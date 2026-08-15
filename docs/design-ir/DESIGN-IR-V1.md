# LUMI AI Design OS — Design IR / Operation Schema V1

> Node: NODE-13  
> Status: IMPLEMENTED / VALIDATING  
> Date: 2026-08-16  
> Executable contract: `apps/api/src/lumi_api/design_ir/`

## 1. Why Design IR exists

A production design agent cannot treat PixiJS objects, browser DOM nodes, provider response JSON or an image prompt as the durable design truth.

LUMI therefore introduces a **renderer-neutral** Design Intermediate Representation (Design IR):

```text
User / Agent intent
        ↓
Typed DesignOperationBatch
        ↓
Pure Design IR operation engine
        ↓
DesignIRDocument revision N+1
        ↓
Canvas adapter / renderer / export adapter
```

The renderer reads Design IR. It does not own product truth.

This boundary lets the same design be edited by users/agents, rendered by Canvas Engine, persisted as DesignDocumentVersion, compared, replayed, exported and migrated without serializing PixiJS runtime internals.

## 2. Version axes

Document schema:

```text
spec_version = lumi.design-ir/1.0
```

Operation schema:

```text
schema_version = lumi.design-op/1.0
```

Document revision:

```text
revision = 1, 2, 3, ...
```

These are different concepts:

- schema version = shape/semantic compatibility of the contract;
- revision = optimistic-concurrency/content version of one document.

A compatible renderer may support several historical schema versions through explicit migration/upcasting. It must never reinterpret an unknown major version silently.

## 3. Coordinate system

V1 freezes one logical editing coordinate space:

```text
coordinate_space = logical_px
```

`logical_px` is renderer-independent design space. It is not physical CSS device pixels and not print millimeters.

Rules:

- all node geometry is expressed in logical pixels;
- transforms use degrees for rotation/skew;
- image crop rectangles are normalized 0..1 values;
- export adapters convert logical pixels into device/output coordinates;
- print DPI/physical units are export concerns, not mutable Scene Graph semantics.

## 4. Document root

`DesignIRDocument` fields:

```text
spec_version
document_id UUIDv7
revision >= 1
coordinate_space = logical_px
pages[]
nodes[]
metadata{}
```

`document_id` is stable across revisions.

`nodes` is serialized in canonical UUID order. Visual stacking/order is **not** inferred from array order; it is defined by each container's ordered `children` list.

## 5. Stable IDs

Application-created document/node/operation IDs use UUIDv7.

Rules:

- node IDs survive movement, style changes and content edits;
- moving a node does not create a new node identity;
- a cloned/new design element receives a new ID;
- IDs are references, not ordering or authorization signals;
- runtime renderer object IDs are never persisted as Design IR identity.

## 6. Scene Graph

V1 has seven typed node kinds:

```text
page
frame
group
text
image
shape
vector
```

Every node has:

```text
id
kind
name
parent_id
visible
locked
opacity
transform
semantic_tags[]
```

### Containers

```text
PageNode
FrameNode
GroupNode
```

Containers own ordered `children[]` IDs.

### Graph invariants

A valid document must satisfy all of the following:

1. every node ID is unique;
2. every `PageNode` is listed exactly once in `pages`;
3. pages have no parent;
4. every non-page node has exactly one container parent;
5. every child reference resolves to a real node;
6. child `parent_id` and parent `children[]` agree bidirectionally;
7. a child appears at most once in a container;
8. the graph is acyclic;
9. every node is reachable from a page;
10. there are no hidden/orphan subgraphs.

The Pydantic document validator enforces these invariants after every atomic operation batch.

## 7. Geometry primitives

### `Transform2D`

```text
x
y
rotation_deg
scale_x / scale_y (non-zero)
skew_x_deg / skew_y_deg
```

Negative scale is permitted for mirroring; zero scale is rejected because it destroys invertibility/useful hit-testing semantics.

### `Size2D`

```text
width > 0
height > 0
```

Bounds are finite and capped to prevent pathological payloads.

### `NormalizedRect`

Used by image crop:

```text
x, y, width, height ∈ [0,1]
x + width <= 1
y + height <= 1
```

## 8. Paint / style primitives

V1 supports:

```text
SolidPaint
LinearGradientPaint
StrokeStyle
ShadowEffect
TextStyle
```

Colors are normalized sRGB RGBA components in `[0,1]`.

Gradient stops must be ordered by position.

Paint may carry a logical `token_ref`; token interpretation/brand constraint enforcement is a separate layer and does not replace resolved visual values.

## 9. Page

A `PageNode` is a top-level design surface:

```text
size
background?
children[]
```

V1 does not add/delete/move pages through generic node operations. Page lifecycle gets an explicit contract when multi-page workflow semantics are finalized rather than being hidden inside `add_node/remove_node`.

## 10. Frame

A `FrameNode` is a sized container:

```text
size
children[]
clip_content
fill?
stroke?
corner_radius
shadows[]
```

Frames are the main composition/container primitive for panels, sections, cards, artboards-inside-pages and generated modules.

## 11. Group

A `GroupNode` is a structural container without an explicit size:

```text
children[]
```

Its visual bounds are derived by the renderer/layout engine from descendants.

## 12. Text

A `TextNode` stores plain text plus typed text style:

```text
size
text
font_family
font_asset_id?
font_size
font_weight
italic
line_height
letter_spacing
align
vertical_align
color
```

Design IR stores plain content, not HTML. Rich-text span modeling is deliberately deferred until the editor requirements are frozen.

## 13. Image

An `ImageNode` stores:

```text
size
asset_id
fit = cover | contain | fill
crop?
```

It references a tenant-owned Asset by ID.

It does **not** persist:

```text
signed URL
provider CDN token
browser Blob URL
base64 image bytes
Pixi Texture object
```

Storage/runtime adapters resolve `asset_id` at render/export time.

## 14. Shape

A `ShapeNode` supports:

```text
rectangle
ellipse
line
```

with size/fill/stroke/corner radius as applicable.

More complex geometry belongs to `VectorNode` or future shape versions.

## 15. Vector

A `VectorNode` stores a bounded path-data string plus:

```text
size
fill?
stroke?
fill_rule
```

It stores vector path data, not arbitrary SVG markup/script/document content. SVG import must sanitize/normalize external markup before producing Design IR.

## 16. No arbitrary JSON Patch

Agent/user mutation is **not** a generic JSON Patch/path-value protocol.

V1 freezes 16 explicit operation kinds:

```text
add_node
remove_node
move_node
reorder_children
set_transform
set_size
set_appearance
set_lock
rename_node
set_text
set_text_style
set_image_asset
set_image_crop
set_fill
set_stroke
set_page_background
```

This is intentionally more verbose than arbitrary patching because each mutation has stable semantics, validation and future authorization/constraint hooks.

A model cannot write `/nodes/3/foo` and hope the current JSON layout still means the same thing next month.

## 17. Operation batch

`DesignOperationBatch`:

```text
schema_version = lumi.design-op/1.0
operation_id UUIDv7
document_id
base_revision
actor
correlation_id?
operations[1..1000]
```

Actor:

```text
kind = user | agent | system
actor_id required for user/agent
```

The `operation_id` is the stable command/batch identity for audit/idempotency/application orchestration. Persistence of processed operation IDs belongs to the application/persistence adapter.

## 18. Optimistic concurrency

Every batch declares:

```text
base_revision
```

The pure engine requires:

```text
batch.document_id == document.document_id
batch.base_revision == document.revision
```

Otherwise it raises `RevisionConflict`.

This mirrors NODE-10/NODE-11 optimistic concurrency but at the Design IR operation level.

A caller must refetch/rebase/replan instead of blindly overwriting a newer design revision.

## 19. Atomic batch

An **atomic batch** has all-or-nothing semantics:

```text
revision N
  + op 1
  + op 2
  + ...
  + op K
        ↓ all valid
revision N+1
```

The revision increments **once per successful batch**, not once per individual operation.

If any operation fails:

```text
no new DesignIRDocument is produced
the input document remains unchanged
```

The persistence adapter must apply the same transaction boundary when storing the resulting DesignDocumentVersion / ArtifactVersion / event records.

## 20. Structural operations

### `add_node`

Requires:

- unique new node ID;
- non-page node in V1;
- `node.parent_id == parent_id`;
- parent is an editable container;
- new Frame/Group starts with empty children;
- insertion index is valid.

A subtree is built parent-first through multiple typed operations in one batch.

### `remove_node`

- cannot remove a page in V1;
- non-empty containers require `recursive=true`;
- locked nodes/descendants reject deletion.

### `move_node`

- cannot move a page in V1;
- source/target containers must be editable;
- self-parent and descendant-parent moves are rejected;
- after removal, `index` is interpreted against the target container's remaining children.

### `reorder_children`

The supplied ordered IDs must contain exactly the current child set, once each. This prevents accidental orphaning through a partial reorder payload.

## 21. Lock semantics

`locked` is an editing constraint, not an authorization primitive.

Normal content/structural operations reject a locked node. `set_lock` itself may unlock a locked node so the editor is not permanently trapped.

Who is permitted to unlock or override locks is an application/constraint policy decision and can be stricter than the pure engine.

## 22. Canonical serialization

`canonical_json(document)` uses:

```text
Pydantic JSON normalization
sorted object keys
canonical node ordering by UUID string
compact separators
UTF-8
NaN/Infinity forbidden
```

`content_hash_sha256(document)` computes SHA-256 over that canonical UTF-8 JSON.

Uses:

- DesignDocumentVersion content hash;
- provenance checks;
- deterministic comparison/caching;
- detecting unintended serialization drift.

The content hash includes document revision because it hashes the complete serialized document contract.

## 23. Finite numeric policy

Geometry uses finite floating-point values because canvas geometry is not money/accounting.

Rules:

- NaN and Infinity are rejected;
- zero scale is rejected;
- sizes/ranges are bounded;
- normalized crop stays within its unit square;
- billing/cost continues to use Decimal in domain/database/event contracts.

## 24. Renderer boundary

The Design IR package must not import:

```text
PixiJS / browser DOM
SQLAlchemy / asyncpg / Alembic
LangGraph / LangChain
OpenAI / Anthropic
object storage SDKs
```

Canvas Engine implements an adapter conceptually like:

```text
DesignIRDocument -> RenderTree/Pixi scene
```

User canvas gestures produce typed DesignOperations conceptually like:

```text
Pixi interaction -> DesignOperationBatch -> application service -> new IR revision
```

Pixi object mutation is never the durable source of truth.

## 25. Agent boundary

Agent Planner/Executor receives the Design IR schema + operation schema and emits typed operations.

It must not:

- emit arbitrary JSON Patch;
- mutate database rows directly;
- return Pixi runtime objects;
- bypass `base_revision`;
- invent storage URLs instead of `asset_id` references.

A future constraint/policy layer can validate a proposed batch before the pure operation engine applies it.

## 26. Persistence mapping

NODE-10 already provides:

```text
design_documents
design_document_versions
artifacts
artifact_versions
artifact_edges
artifact_provenance
```

Recommended application transaction for a Design IR edit:

```text
BEGIN
  load current immutable DesignDocumentVersion
  verify expected/base revision
  validate proposed DesignOperationBatch
  apply pure operation engine
  store new DesignDocumentVersion(content_json, content_hash)
  move mutable document head pointer
  write audit/provenance/outbox facts
COMMIT
```

Historical version JSON is immutable.

## 27. JSON Schema export

Pydantic is the executable source of truth.

Generate machine-readable schemas with:

```bash
PYTHONPATH=apps/api/src python tools/node13/export_design_schemas.py
```

Outputs:

```text
design-ir-v1.schema.json
design-operation-batch-v1.schema.json
```

These schemas are suitable inputs for Agent tool definitions, TypeScript code generation, contract documentation and test fixtures. Generated artifacts do not replace the Python source contract.

## 28. Security / payload limits

V1 bounds potentially dangerous payload classes:

```text
nodes <= 100,000
pages <= 1,000
operations per batch <= 1,000
text <= 200,000 chars/node
vector path <= 500,000 chars/node
semantic tags <= 64
shadows <= 16
```

These schema limits are not substitutes for request-size/rate/cost limits at the HTTP/application boundary.

## 29. Deferred from V1

Not frozen prematurely:

- rich-text span model;
- arbitrary SVG document model;
- boolean vector operations;
- component/instance semantics;
- auto-layout engine;
- responsive constraint solver;
- variables/expressions engine;
- animation/timeline;
- multi-user CRDT/OT;
- comments/presence;
- page create/delete/move operations;
- print physical-unit document space;
- renderer-specific filters/shaders.

These can extend the IR through explicit versions/typed nodes/operations rather than leaking ad-hoc fields into V1.

## 30. Definition of Done

NODE-13 is COMPLETE only when:

```text
renderer-neutral DesignIRDocument
+ seven typed node kinds
+ graph invariants
+ finite geometry/style primitives
+ sixteen typed operations
+ atomic batch engine
+ optimistic base_revision
+ canonical JSON/hash
+ JSON Schema exporter
+ executable graph/operation tests
+ renderer/ORM/agent-runtime dependency purity
+ repository CI/security green
+ stacked NODE-09/10/11/12 dependencies resolved
+ merged and NODE index updated
```

Until then it remains `VALIDATING` or `BLOCKED_EXTERNAL / VALIDATING` according to evidence.
