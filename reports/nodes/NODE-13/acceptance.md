# NODE-13 — Acceptance Evidence

> Status: **VALIDATING**  
> Branch: `feat/node-13-design-ir`  
> Stacked Base: `feat/node-12-event-contract` / PR #78  
> Node: Design IR / Operation Schema  
> Date: 2026-08-16

## Scope implemented

NODE-13 introduces the renderer-neutral editable design truth shared by Agent planning, Canvas rendering, persistence and export.

Implemented:

- strict/frozen Design IR contract independent of Pixi/browser runtime;
- `lumi.design-ir/1.0` document schema;
- `lumi.design-op/1.0` operation-batch schema;
- UUIDv7 document/node/operation identities;
- `logical_px` renderer-neutral coordinate space;
- seven typed Scene Graph node kinds;
- graph integrity validation for parents/children/pages/reachability/cycles;
- finite geometry, crop, paint, stroke, shadow and text primitives;
- Asset-ID image references instead of URLs/runtime textures;
- 16 explicit typed operations instead of arbitrary JSON Patch;
- actor/correlation metadata on operation batches;
- optimistic `base_revision` conflict handling;
- pure atomic all-or-nothing batch engine;
- locked-node edit protection;
- structural move/remove/reorder safeguards;
- canonical JSON serialization and SHA-256 content hashing;
- deterministic JSON Schema exporter for Design IR and operation batches;
- executable Scene Graph/operation tests;
- dependency-purity validator forbidding renderer/ORM/Agent-runtime/provider coupling;
- dedicated frozen-install/schema-export GitHub Actions workflow.

Canonical documentation:

```text
docs/design-ir/DESIGN-IR-V1.md
```

## Scene Graph contract

V1 node kinds:

```text
page
frame
group
text
image
shape
vector
```

A valid document requires:

- unique UUIDv7 node identities;
- `pages[]` exactly matches every PageNode;
- pages are roots;
- every non-page node has exactly one container parent;
- parent `children[]` and child `parent_id` agree;
- all child references resolve;
- no duplicate child references;
- no scene graph cycles;
- every node reachable from a page.

## Operation registry

V1 freezes exactly 16 operations:

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

This deliberately rejects arbitrary JSON Patch semantics so Agent/frontend/runtime implementations cannot couple themselves to incidental JSON array/object layout.

## Atomic revision semantics

A `DesignOperationBatch` declares:

```text
operation_id UUIDv7
document_id
base_revision
actor
correlation_id?
operations[1..1000]
```

The pure engine requires exact document/revision match, applies all operations to an isolated working map, revalidates the entire Scene Graph and only then returns revision `N+1`.

If any operation fails:

```text
no result revision is produced
the input immutable document remains unchanged
```

A successful batch increments revision exactly once, regardless of how many operations it contains.

## Canonical content evidence

`canonical_json()`:

- serializes through Pydantic JSON normalization;
- sorts object keys;
- canonicalizes document node tuple by UUID string;
- uses explicit container `children[]` for visual order;
- uses compact UTF-8 JSON;
- forbids NaN/Infinity.

`content_hash_sha256()` hashes this complete canonical document representation.

Executable tests verify two logically identical documents with different input node tuple ordering produce the same canonical JSON/hash.

## Renderer and Agent boundaries

`lumi_api.design_ir` must not import:

```text
Pixi/PixiJS
SQLAlchemy / asyncpg / Alembic
LangGraph / LangChain
OpenAI / Anthropic
object-storage SDKs
```

Renderer adapters consume Design IR. Canvas interactions and Agents propose typed operations. Neither renderer runtime objects nor arbitrary model-generated JSON patches become durable product truth.

## Machine-readable schemas

`tools/node13/export_design_schemas.py` generates:

```text
design-ir-v1.schema.json
design-operation-batch-v1.schema.json
```

The dedicated workflow regenerates these schemas, verifies both files are non-empty valid JSON and uploads them as a CI artifact. They are derived artifacts; executable Pydantic source remains canonical.

## Executable tests

`apps/api/tests/test_design_ir_contract.py` covers:

1. valid empty document / one PageNode / stable content hash;
2. add TextNode atomically with one revision increment;
3. multi-operation batch still produces only one new revision;
4. stale base revision rejection without input mutation;
5. later-operation failure rolls back the entire pure batch;
6. missing Scene Graph child rejection;
7. nested Frame/Text creation and cross-container movement;
8. recursive subtree removal semantics;
9. locked-node edit rejection and explicit unlock behavior;
10. canonical node ordering independent of input tuple ordering;
11. strict operation schema / UUIDv7 operation identity;
12. renderer/ORM/Agent-runtime/provider dependency purity.

`tools/node13/validate_design_ir.py` additionally asserts:

- exact 16-operation registry;
- generated JSON Schema contains both contract versions and every operation discriminator;
- UUIDv7/`logical_px`/canonical-hash baseline;
- architecture dependency purity;
- canonical contract documentation contains the required invariants.

## Validation status

Implementation is complete enough for repository validation, but hosted execution has not yet been accepted as evidence for NODE-13.

The preceding stacked chain currently contains open PRs #75–#78. NODE-13 must obtain its own workflow/CI evidence; it must not inherit a PASS or external-block conclusion from an earlier node.

## Acceptance checklist

- [x] renderer-neutral Design IR contract implemented.
- [x] seven typed Scene Graph nodes implemented.
- [x] Scene Graph integrity invariants implemented.
- [x] finite geometry/style/crop primitives implemented.
- [x] Asset-ID image reference boundary implemented.
- [x] 16 typed operations implemented.
- [x] arbitrary JSON Patch excluded from V1.
- [x] UUIDv7 operation/document/node identity enforced.
- [x] optimistic base-revision contract implemented.
- [x] atomic all-or-nothing batch engine implemented.
- [x] locked-node/structural safeguards implemented.
- [x] canonical JSON/SHA-256 content hash implemented.
- [x] JSON Schema exporter implemented.
- [x] executable contract tests committed.
- [x] renderer/ORM/Agent-runtime/provider dependency purity enforced.
- [x] dedicated NODE-13 workflow committed.
- [ ] frozen repository install passes for this PR.
- [ ] NODE-13 deterministic validator passes on Python 3.12.
- [ ] Design IR pytest passes on Python 3.12.
- [ ] schema export/JSON parse gate passes.
- [ ] repository CI/security gates pass.
- [ ] stacked NODE-09/10/11/12 dependencies resolve and merge.
- [ ] NODE-13 merged and NODE index updated to COMPLETE.

NODE-13 remains `VALIDATING`, not `COMPLETE`.
