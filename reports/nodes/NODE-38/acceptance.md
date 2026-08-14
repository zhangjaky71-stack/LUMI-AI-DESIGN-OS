# NODE-38 — Design IR Runtime Acceptance

> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Branch: `node-38-design-ir-runtime`  
> Release branch: `node-38-design-ir-runtime-release`  
> Draft PR: #38  
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
| 2k nodes / 100 ops benchmark | `scripts/benchmark_design_ir_runtime.py` | IMPLEMENTED; hosted result blocked |
| Static contract validator | `scripts/validate_design_ir_runtime.py` | IMPLEMENTED |
| Dedicated CI | `.github/workflows/design-ir-runtime.yml` | IMPLEMENTED; hosted runner blocked |

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

## Hosted CI evidence — 2026-08-14

Draft PR #38 triggered `Design IR Runtime` workflow run `31781688458` for release head `4729c4632c76e56d8a9210d6075e7f73bf8550af`.

Observed jobs:

- `design-ir-contract`: **failure before runner start**; zero workflow steps executed; `runner_id=0`.
- `design-ir-quality`: skipped because the contract dependency did not run successfully.
- `design-ir-benchmark`: skipped because the quality dependency did not run successfully.

GitHub check annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased.

This is an **external GitHub Actions account/billing/spending-limit blocker**. It is not evidence of a Design IR Runtime test, typecheck, Ruff, Pyright, conformance or benchmark failure because none of those steps started.

## Current disposition

NODE-38 remains **IMPLEMENTED / VALIDATING / not COMPLETE**. The implementation, tests, fixture, validator, benchmark harness and CI definitions are committed. Completion is intentionally withheld until the hosted gates can actually execute and return green.
