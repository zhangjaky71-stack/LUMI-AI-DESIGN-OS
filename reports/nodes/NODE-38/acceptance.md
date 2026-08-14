# NODE-38 — Design IR Runtime Acceptance

> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Branch: `node-38-design-ir-runtime`  
> Base: `node-37-agent-team-release`

## Scope evidence

| Requirement | Evidence | State |
| --- | --- | --- |
| Reuse frozen NODE-13 Design IR contract | `packages/design-ir/src/types.ts` | IMPLEMENTED |
| TS immutable executor | `packages/design-ir/src/executor.ts` | IMPLEMENTED |
| Python executor mirror | `services/domain/src/lumi_domain/design_ir_runtime.py` | IMPLEMENTED |
| Atomic all-or-nothing batch | executor + rollback tests | IMPLEMENTED |
| Optimistic document version check | executor + version-conflict tests | IMPLEMENTED |
| Parser / structural validation | `validation.ts`, `design_ir_document.py` | IMPLEMENTED |
| Graph cycle / reference validation | parser tests | IMPLEMENTED |
| Canonical serialization / SHA-256 | `canonical.ts`, `design_ir_canonical.py` | IMPLEMENTED |
| Unicode NFC / ephemeral metadata policy | canonical modules + tests | IMPLEMENTED |
| TS/Python conformance vector | `fixtures/design-ir/node-38-conformance.json` | IMPLEMENTED |
| Semantic diff | `diff.ts`, Python runtime | IMPLEMENTED |
| Explicit migration chain | `migrations.ts`, Python migration registry | IMPLEMENTED |
| Provenance preservation | migration tests | IMPLEMENTED |
| Semantic selector query | `query.ts`, `design_ir_document.py` | IMPLEMENTED |
| Spatial adapter boundary | `query.ts`, `design_ir_document.py` | IMPLEMENTED |
| Command history / undo / redo | `history.ts` + tests | IMPLEMENTED |
| 2k nodes / 100 ops benchmark | `scripts/benchmark_design_ir_runtime.py` | IMPLEMENTED; hosted result pending |
| Static contract validator | `scripts/validate_design_ir_runtime.py` | IMPLEMENTED |
| Dedicated CI | `.github/workflows/design-ir-runtime.yml` | IMPLEMENTED; hosted execution pending |

## Frozen-operation coverage

The runtime implements the NODE-13 V1 operation set without introducing a second protocol:

- CREATE_NODE
- DELETE_NODE
- SET_PROPERTY
- MOVE_NODE
- RESIZE_NODE
- ROTATE_NODE
- REORDER_NODE
- REPARENT_NODE
- REPLACE_ASSET
- SET_TEXT
- APPLY_STYLE
- BATCH

Constraint-rule evaluation is intentionally not duplicated here; hard/soft design rules remain NODE-39.

## Acceptance gates

Required before marking COMPLETE:

1. `design-ir-contract` executes green on the hosted runner.
2. `design-ir-quality` executes TypeScript/Python conformance, pytest, Ruff and Pyright green.
3. `design-ir-benchmark` records the 2,000-node / 100-operation median within the 1,500 ms hosted baseline budget.
4. No contract drift is found against NODE-13/14/15.
5. Release PR remains stack-compatible with `node-37-agent-team-release`.

## Current disposition

Repository implementation and validation artifacts are present. This report deliberately does **not** mark NODE-38 COMPLETE until the hosted GitHub gates actually execute successfully. If GitHub Actions is prevented from starting by the existing account billing/spending-limit condition, that condition must be recorded as an external blocker rather than reclassified as a code test failure.
