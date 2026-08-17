# NODE-38 Acceptance — Design IR Runtime

## Status

`IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL`

The implementation is stacked on `feat/node-37-agent-team`. Hosted GitHub Actions PASS is not
claimed.

## Delivered

- TypeScript Canvas-facing Design IR runtime;
- Python Agent/service conformance runtime;
- shared cross-language canonical/hash fixtures;
- parse + structural/graph validation;
- immutable external snapshot semantics;
- private transaction draft execution;
- operation version conflict protection;
- atomic BATCH with operation-id deduplication;
- Constraint Engine preflight hook;
- semantic node query selectors;
- semantic diff categories for Version UI/Audit;
- deterministic `1.0 -> 1.1 -> 2.0` migration chain with provenance;
- command undo/redo snapshot history;
- non-finite number rejection;
- deterministic canonical serialization and SHA-256;
- 2k-node / 100-operation reference benchmark;
- static architecture validator;
- dedicated TS + Python CI gate;
- five explicit production integration gaps.

## Local evidence

The exact NODE-38 source set was validated in an isolated scratch workspace.

### Python

```text
PYTHONPATH=packages-py pytest -q packages-py/tests/test_design_ir_node38.py
13 passed
python -m compileall: PASS
NODE38_DESIGN_IR_RUNTIME_VALIDATION_PASS
```

Coverage includes parse/serialize/parse stability, shared fixture hashes, copy-on-write mutation,
version conflicts, atomic batch rollback, constraint preflight, semantic selectors/diff, migration,
command history, invalid floats, randomized reorder invariants and the reference benchmark.

### TypeScript

Local isolated strict compile using the available TypeScript 5.8.3 compiler passed with repository-
equivalent strict flags. A compiled Node smoke/conformance runner produced:

```text
NODE38_TS_CONFORMANCE_PASS fixtures=4
```

All four shared fixture canonical strings and SHA-256 hashes matched the Python-generated expected
values.

### Reference benchmark

```text
TypeScript:
  parse_2k_ms ~= 19.4
  batch_100_ms ~= 90.3

Python:
  parse_2k_ms ~= 16.1
  batch_100_ms ~= 93.9
```

These measurements are not promoted to release SLOs until NODE-08 standard-machine calibration is
available.

Local Ruff, Pyright, pnpm 11, repository TypeScript 6.0.3 and Vitest execution are not claimed from
this isolated environment. The hosted workflow is responsible for those gates.

## Hosted runner evidence

The first dedicated hosted workflow attempt for PR #105 is run `32008876627`. Its
`design-ir-runtime` job `95323953486` ended with:

```text
status=completed
conclusion=failure
steps=[]
```

No checkout, pnpm install, TypeScript typecheck, Vitest, uv install, Python tests, validator, Ruff or
Pyright step executed. This is classified as `BLOCKED_EXTERNAL`, consistent with the hosted runner-
allocation failure already observed on preceding nodes. It is not a NODE-38 code or test failure.

## Security and correctness assertions

- input snapshots are not mutated by public runtime APIs;
- no Pixi, React, model-provider, LangChain or LangGraph dependency is allowed in Design IR core;
- non-finite numeric values fail validation;
- reparenting cannot create a cycle;
- BATCH cannot return a partial document version;
- nested BATCH is rejected in V1;
- operation IDs are deduplicated;
- callers cannot bypass expected-document-version checks;
- canonical hash excludes non-semantic runtime/UI metadata;
- migration is an explicit step chain, not target-version guessing.

## Production gaps

Five items remain deliberately open:

1. production NODE-14/NODE-39 constraint adapter;
2. NODE-15 durable Artifact/Version commit adapter;
3. downstream Canvas/Agent/Export direct-mutation migration audit;
4. high-performance spatial index adapter;
5. NODE-08 standard-hardware performance gate calibration.

See `reports/nodes/NODE-38/gap-ledger.json`.

## Hosted acceptance gate

Before NODE-38 may become COMPLETE, a real hosted runner must execute frozen pnpm install,
TypeScript 6.0.3 typecheck, Vitest, frozen uv install, Python 3.12 tests,
`NODE38_DESIGN_IR_RUNTIME_VALIDATION_PASS`, Ruff, Pyright and gap-ledger parse.

Next node after acceptance: **NODE-39 — Constraint Validator**.
