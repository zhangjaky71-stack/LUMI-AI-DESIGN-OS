# LUMI Design IR V1

> Contract status: **FROZEN FOR NODE-13 IMPLEMENTATION / VALIDATING**  
> Schema version: `1.0`  
> Canonicalization: `LUMI_CANONICAL_JSON_V1`  
> Range indexing: `UNICODE_CODE_POINT`

## 1. Purpose

Design IR is the renderer/provider-independent contract between Agent intent, structured design operations, constraint validation, Canvas compilation, Artifact versioning and Export.

```text
Agent intent
  -> DesignOperation
  -> Design IR document
  -> Constraint pre/postflight
  -> Canvas compiler / renderer
  -> Artifact / Export
```

The persisted representation MUST NOT contain Pixi scene objects, React/DOM identity, texture handles, presigned URLs, hover/selection state or viewport camera state.

## 2. Canonical contract files

```text
contracts/design-ir/v1/
├── type-manifest.json
├── design-document.schema.json
├── operation.schema.json
├── fixtures/corpus.json
└── generated/
    ├── types.py
    └── types.ts
```

`type-manifest.json` is the common vocabulary source for generated Python/TypeScript enum/union types. JSON Schema remains the canonical structural interchange contract.

## 3. Document identity

A V1 document contains:

```text
schema_version = "1.0"
document_id
unit = "px"
root_id
nodes: ID -> Node
resources
metadata
```

Node map keys MUST equal `node.id`. Nodes are addressed by stable IDs; parent/child order is represented explicitly rather than inferred from nested JSON position.

## 4. Node kinds

V1 freezes exactly these kinds:

```text
DOCUMENT_ROOT
FRAME
GROUP
TEXT
IMAGE
SHAPE
VECTOR_PATH
VIDEO
MASK
GUIDE
COMPONENT
INSTANCE
```

Unknown kinds are rejected under major version 1. They are never silently coerced to GROUP.

## 5. Node structural invariants

The reference validator enforces:

1. one existing `root_id`;
2. root kind is `DOCUMENT_ROOT`;
3. root has `parent_id = null`;
4. every non-root node has one existing parent;
5. parent `children[]` and child `parent_id` agree in both directions;
6. no duplicate child IDs;
7. every child reference exists;
8. no graph cycle;
9. every node is reachable from root;
10. every numeric value is finite;
11. resource references resolve to the correct registry;
12. INSTANCE references a COMPONENT node;
13. IMAGE mask references a MASK node;
14. TEXT spans obey the V1 Unicode range policy.

## 6. Resource model

Design IR references logical resources only:

```text
assets
fonts
brand_tokens
styles
```

Binary content remains in Asset/Object Storage. IMAGE/VIDEO nodes persist resource IDs, not temporary signed URLs.

## 7. Text and Unicode

V1 rich-text span ranges use **Unicode code-point offsets**.

Python naturally indexes strings by code point. JavaScript/TypeScript implementations MUST convert through `Array.from(text)` before range operations, because native JS string indexing uses UTF-16 code units.

Example:

```text
text = "你好👋设计"
code-point length = 5
[2, 3) = "👋"
```

Spans must be ordered, non-overlapping and inside the code-point length.

## 8. Operations

V1 freezes:

```text
CREATE_NODE
DELETE_NODE
SET_PROPERTY
MOVE_NODE
RESIZE_NODE
ROTATE_NODE
REORDER_NODE
REPARENT_NODE
REPLACE_ASSET
SET_TEXT
APPLY_STYLE
BATCH
```

Every operation carries:

```text
operation_id
type
target_ids
expected_document_version
payload
reason
```

`SET_PROPERTY` cannot mutate `id`, `kind`, `parent_id` or `children`; structural changes must use their dedicated operations.

## 9. Version and concurrency semantics

Document version is persistence/application state, not duplicated inside the Design IR JSON body.

The operation executor receives the current version separately and rejects stale `expected_document_version` values.

A successful primitive operation consumes exactly one new document version.

A successful BATCH also consumes exactly one new document version, regardless of child count.

## 10. BATCH atomicity

BATCH requires `atomic=true`.

Execution occurs on a deep working copy:

```text
validate current document
-> copy
-> apply all child operations against the same expected version
-> validate final document
-> compute hash
-> return one new version
```

Any child failure or final structural/resource failure discards the whole working copy. The caller's source document is never mutated.

NODE-14 adds hard/soft/advisory constraint enforcement around this transaction; NODE-13 already guarantees structural atomicity.

## 11. Canonical serialization and hash

`LUMI_CANONICAL_JSON_V1` uses:

- UTF-8 JSON;
- object keys sorted lexicographically;
- compact separators;
- finite numeric values only;
- negative zero normalized to zero;
- no NaN/Infinity;
- ephemeral UI metadata removed from `metadata` objects;
- SHA-256 over canonical UTF-8 bytes.

Canonical hash is used by cache, provenance, version comparison and later artifact lineage.

The canonical form intentionally excludes UI-only keys such as hover, selection, selection marquee, open panel, cursor, viewport/camera, DOM element IDs and renderer texture IDs.

## 12. Diff semantics

Canonical hash answers equality, not user-facing meaning.

Semantic version comparison should report:

```text
node added/removed
property changed
geometry changed
asset replaced
text changed
constraint reference changed
```

NODE-38 owns the production diff/migration runtime.

## 13. Compatibility policy

### `1.x`

Backward-compatible additions only. Consumers must ignore unknown optional metadata fields but MUST NOT reinterpret an unknown node kind or operation type.

### `2.0`

Breaking changes are allowed only with an explicit deterministic migration path.

Persisted Artifact/DesignDocument versions retain the schema version under which they were produced.

## 14. Migration policy

No historical schema file is rewritten after release.

For a future major upgrade:

```text
parse old version
-> deterministic migrate_v1_to_v2(document)
-> validate v2
-> canonicalize v2
-> record source/target schema versions in provenance
```

Migration must not call models/providers/network services and must produce the same output for the same input.

The fixture `v1-migration-fixture` exists to anchor future migration compatibility tests.

## 15. Fixtures

The V1 corpus includes at least:

```text
single-frame-poster
multi-frame-social-kit
logo-and-qr-locks
chinese-text-codepoints
group-mask
image-crop
component-instance
invalid-parent-cycle
missing-asset-reference
v1-migration-fixture
```

Negative fixtures are first-class contract evidence, not malformed examples hidden outside CI.

## 16. Generated language types

`scripts/generate_design_ir_types.py` reads only `type-manifest.json` and deterministically emits:

```text
contracts/design-ir/v1/generated/types.py
contracts/design-ir/v1/generated/types.ts
```

CI runs `--check`; generated drift fails the gate.

The TypeScript generated helper uses `Array.from()` for code-point semantics.

## 17. Reference runtime ownership

`services/design-ir/src/lumi_design_ir` provides a dependency-free executable reference for:

```text
canonical serialization/hash
structural graph validation
resource reference validation
Unicode span validation
operation execution
BATCH atomicity
```

It is a contract reference, not the future optimized Canvas runtime. NODE-38 may optimize implementation but must remain conformant.

## 18. Explicit non-ownership

NODE-13 does NOT own:

- hard/soft design constraints -> NODE-14/NODE-39;
- ArtifactVersion/Branch/Provenance lifecycle -> NODE-15/NODE-42;
- renderer scene objects -> NODE-40/41;
- brand rule evaluation -> NODE-43;
- image/video generation -> NODE-46/48;
- export rendering -> NODE-49.

## 19. Validation gate

`.github/workflows/design-ir-contract.yml` performs:

```text
Python 3.12 compileall
manifest/schema/fixture validator
generated type drift check
stdlib reference runtime tests
frozen pnpm install
TypeScript compile of generated contract
```

It intentionally does not require the stale upstream `uv.lock`.
