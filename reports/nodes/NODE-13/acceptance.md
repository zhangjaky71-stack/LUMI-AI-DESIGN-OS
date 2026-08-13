# NODE-13 Acceptance Report — Design IR V1

> Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**  
> Branch: `node-13-design-ir`  
> Official node: **NODE-13 — Design IR Specification V1**  
> Base: `node-12-event-contract`

## 1. Correction applied

An earlier extra Application Services foundation was mistakenly labeled NODE-13. That PR has been reclassified as `EXTRA-APP-01`; this branch restores the frozen roadmap where NODE-13 is Design IR V1 and NODE-14 is Constraint Engine V1.

No previous code was deleted. The extra application layer is no longer in the official NODE-13 dependency path.

## 2. Delivered contract artifacts

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

Published JSON Schema dialect: Draft 2020-12.

## 3. Frozen V1 vocabulary

### Node kinds — 12

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

### Operations — 12

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

### Semantic roles

Built-ins are frozen with `custom:*` namespace escape hatch.

## 4. Structural invariants implemented

Reference runtime rejects:

- root missing or not DOCUMENT_ROOT;
- root with parent;
- node map key/id mismatch;
- unknown node kind;
- missing parent;
- parent/children disagreement;
- duplicate/missing child refs;
- cycles;
- unreachable nodes;
- non-finite numbers;
- missing asset/font/style refs;
- invalid MASK ref;
- invalid COMPONENT/INSTANCE ref;
- invalid Unicode code-point rich-text spans.

## 5. Canonical serialization/hash

Implemented `LUMI_CANONICAL_JSON_V1`:

- deterministic key ordering;
- compact UTF-8 JSON;
- finite numbers only;
- negative zero normalization;
- SHA-256 content hash;
- ephemeral UI metadata excluded.

Renderer/DOM/Pixi identity is not part of the persisted hash contract.

## 6. Unicode policy

V1 range indexing is `UNICODE_CODE_POINT`.

Python helper and generated TypeScript helper are aligned. TypeScript uses `Array.from(value)` so emoji/surrogate pairs do not corrupt span ranges.

## 7. Operation semantics

`apply_operation()`:

- validates source document;
- checks `expected_document_version`;
- deep-copies source;
- applies structured operation(s);
- validates final document;
- computes before/after canonical hashes;
- returns one new document version;
- never mutates caller input.

`SET_PROPERTY` cannot bypass structural operations by directly writing `id/kind/parent_id/children`.

## 8. BATCH semantics

BATCH requires `atomic=true`.

All child operations execute against the same expected source version and the batch consumes exactly one new document version. Any child/final validation failure discards the entire working copy.

This provides structural atomicity; NODE-14 adds constraint atomicity.

## 9. Fixture corpus

Committed 10 named fixtures:

1. single-frame-poster
2. multi-frame-social-kit
3. logo-and-qr-locks
4. chinese-text-codepoints
5. group-mask
6. image-crop
7. component-instance
8. invalid-parent-cycle
9. missing-asset-reference
10. v1-migration-fixture

Corpus includes both positive and negative cases.

## 10. Generated type conformance

`scripts/generate_design_ir_types.py` deterministically generates Python and TypeScript contract types from `type-manifest.json`.

`--check` fails on generated drift.

## 11. Tests implemented

Reference unittest coverage includes:

- fixture breadth;
- all positive fixture validation;
- Unicode code-point behavior with Chinese + emoji;
- canonical hash stability under object-key reorder;
- ephemeral metadata exclusion;
- deterministic MOVE;
- source immutability;
- stale document-version rejection;
- BATCH rollback;
- cycle-producing REPARENT rejection;
- SET_PROPERTY structural-bypass rejection.

## 12. Independent CI gate

`.github/workflows/design-ir-contract.yml` is intentionally independent from the upstream Python uv environment:

```text
Python 3.12 compileall
contract validator
generated types --check
stdlib unittest
existing frozen pnpm install
generated TypeScript tsc compile
```

No new pnpm dependency was added.

## 13. Compatibility policy

- `1.x`: backward-compatible additions only;
- unknown optional metadata may be ignored;
- unknown node kinds/operation types are not silently coerced;
- `2.0`: breaking changes require deterministic explicit migration;
- historical schemas are immutable;
- Artifact/DesignDocument versions preserve source schema version.

## 14. Current external blocker

GitHub hosted Actions cannot currently start because the account's billing/payment or Actions spending limit requires attention. Previous GitHub check annotation stated:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings.

Therefore no real runner PASS is claimed yet.

NODE-13 itself does **not** depend on NODE-10's stale `uv.lock`; its dedicated gate can validate independently once hosted runners are available.

## 15. Acceptance checklist

- [x] V1 Design Document JSON Schema committed.
- [x] V1 Operation JSON Schema committed.
- [x] 12 node kinds frozen.
- [x] 12 operation kinds frozen.
- [x] renderer/provider independence enforced by contract design.
- [x] canonical hash policy implemented.
- [x] Unicode range strategy frozen.
- [x] 10 fixture cases committed.
- [x] Python + TypeScript types generated from one manifest.
- [x] deterministic operation reference runtime implemented.
- [x] BATCH structural atomicity implemented.
- [x] migration/compatibility policy documented.
- [ ] real Design IR Contract GitHub runner PASS.

## 16. Completion gate

After external GitHub Actions recovery:

1. Design IR Contract workflow starts on a real runner;
2. Python compileall PASS;
3. schema/manifest/fixture validator PASS;
4. generated type `--check` PASS;
5. reference unittest PASS;
6. generated TypeScript `tsc` PASS;
7. mark NODE-13 COMPLETE only after evidence is recorded.

Next official node: **NODE-14 — Constraint Engine V1**.
