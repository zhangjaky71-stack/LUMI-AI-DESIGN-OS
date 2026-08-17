# Design IR Runtime V1

## Status

NODE-38 turns the NODE-13 Design IR contract into the only supported mutation runtime for
Agent, Canvas and Export code. The runtime is provider-independent and renderer-independent.

## Runtime surfaces

TypeScript (`packages/design-ir`) is the Canvas-facing implementation. Python
(`packages-py/design_ir`) is the Agent/service conformance implementation. They share
`packages/design-ir/fixtures/conformance-v1.json`.

Both runtimes expose the same semantic operations:

```text
parseDocument / parse_document
validateDocument / validate_document
applyOperation / apply_operation
applyBatch / apply_batch
computeSemanticDiff / compute_semantic_diff
canonicalize
hashDocument / hash_document
migrate
queryNodes / query_nodes
CommandHistory
```

## Mutation invariant

Persisted IR is never mutated in place by callers.

```text
snapshot vN
-> expected_document_version check
-> constraint preflight hook
-> private transaction draft
-> operation execution
-> structural/graph validation
-> semantic diff
-> candidate snapshot vN+1
```

A private transaction draft may be mutated internally for performance. The input object remains
unchanged and no draft escapes if validation fails.

## Batch atomicity

A BATCH has one version transition. Every child operation must target the same expected document
version. Duplicate `operation_id` values, nested BATCH operations, a failed hard preflight, an invalid
target, a graph cycle, or an invalid final graph abort the whole transaction.

No partial snapshot is returned.

## Version conflict

Every mutation carries `expected_document_version`. A mismatch raises:

```text
IR_VERSION_CONFLICT
```

NODE-38 intentionally does not perform implicit CRDT merge.

## Canonical serialization

The cross-language canonical policy is frozen as:

- NFC Unicode normalization for strings and object keys;
- stable ordinal object-key ordering;
- finite numbers only;
- `-0` normalized to `0`;
- numeric canonical precision rounded to 12 decimal places;
- semantic arrays retain order;
- SHA-256 content hash;
- non-semantic metadata excluded:
  `document_version`, command history, applied operation IDs, viewport/selection/cursor and
  `ephemeral:*` / `_ephemeral*` keys.

The same fixture must produce byte-identical canonical text and SHA-256 in TypeScript and Python.

## Semantic query

`queryNodes` / `query_nodes` supports:

- id;
- role;
- kind;
- parent;
- frame ancestry;
- brand binding;
- asset binding;
- locked state.

This is the Agent-facing mechanism for local IR retrieval instead of injecting an entire large
document into a prompt.

## Semantic diff

The runtime emits machine-readable categories:

```text
nodes_added
nodes_removed
properties_changed
text_changed
geometry_changed
asset_replaced
constraints_changed
```

This contract is designed for Version UI, Critic, Audit and Artifact provenance consumers.

## Migration chain

The reference chain is deterministic and explicit:

```text
1.0 -> 1.1 -> 2.0
```

Each step records source canonical content in `metadata.migration_provenance`. NODE-38 does not permit
skipping an unknown intermediate version. When future schemas add real breaking changes, the step
implementation must be replaced with the schema-specific pure transform while keeping the chain.

## Command history

`CommandHistory` stores immutable before/after snapshots for undo/redo. It is runtime state, not a
replacement for NODE-15 durable Artifact/Version provenance.

## Constraint boundary

The executor accepts a deterministic preflight hook. Any returned hard issue aborts before the
candidate snapshot is published. The concrete NODE-14/NODE-39 production adapter is intentionally
tracked as a gap rather than faked in this node.

## Error model

Public runtime errors use stable codes:

```text
IR_SCHEMA_INVALID
IR_GRAPH_CYCLE
IR_REFERENCE_MISSING
IR_VERSION_UNSUPPORTED
IR_OPERATION_INVALID
IR_TARGET_NOT_FOUND
IR_VERSION_CONFLICT
IR_BATCH_FAILED
IR_CONSTRAINT_FAILED
```

Errors carry operation IDs, node IDs and JSON pointers when available. UI callers should expose the
code and safe message, not an internal stack.

## Local reference evidence

Isolated validation completed in the implementation environment:

```text
Python pytest: 13/13 PASS
TypeScript strict compile: PASS (local TypeScript 5.8.3 isolated compile)
TS/Python shared canonical/hash fixtures: 4/4 PASS
TS reference benchmark:
  parse 2k nodes ~= 19.4 ms
  batch 100 ops ~= 90.3 ms
Python reference benchmark:
  parse 2k nodes ~= 16.1 ms
  batch 100 ops ~= 93.9 ms
```

These are reference measurements, not the final release budget. NODE-08 standard-machine calibration
remains required before a hard performance release threshold is claimed.

## Production qualification

NODE-38 freezes the runtime contract. It does not claim completion of the five integration items in
`reports/nodes/NODE-38/gap-ledger.json`.

Next node: NODE-39 Constraint Validator.
