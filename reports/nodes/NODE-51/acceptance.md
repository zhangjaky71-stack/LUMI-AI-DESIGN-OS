# NODE-51 — Auto Repair Acceptance

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

Base: `node-50-visual-critic-release@2991610c91a5ab58ae482a711d62cffee482c9bf`

## Implemented evidence

### Core

- standalone `@lumi/auto-repair-engine`;
- exact policy/version/source pinning;
- hard bounded iteration loop;
- canonical attempted-repair fingerprint set;
- deterministic minimal/cheap/reversible ordering;
- safe aggregate telemetry.

### Constraint and Design IR

- NODE-50 repair actions remain frozen NODE-38 DesignOperations;
- structural repair uses NODE-39 `guardedExecute`;
- no direct mutation of source DesignDocument;
- stale operation/hard lock deny candidate materialization.

### Budget

- decimal string → BigInt micro-dollar arithmetic;
- paid repair requires `BudgetReservationPort`;
- reserve occurs before `GenerativeRepairPort.execute`;
- actual cost settles after execution;
- no NODE-27 shadow ledger is created while NODE-27 remains spec-only.

### Artifact and concurrency

- candidate persisted DRAFT/off-head before re-evaluation;
- exact candidate re-evaluated through NODE-50 profile id/version;
- `EDITED_FROM` lineage semantics with repair metadata;
- PASS/WARN → READY promotion;
- materially improved FAIL_REPAIRABLE → DRAFT promotion for next bounded iteration;
- regression/new Hard/FAIL_HARD/review never replace good branch head;
- promotion uses expected-head CAS;
- concurrent user edit returns STALE_SOURCE rather than force overwrite.

### Database

`0010_auto_repair.sql` includes:

- `auto_repair_policies`;
- `auto_repair_loops`;
- `auto_repair_attempts`;
- exact production profile seeds;
- transactional `promote_auto_repair_candidate` with source-parent validation and branch CAS.

### Tests

```text
NODE-50 exact text repair via NODE-39      -> READY
quality regression                         -> candidate REJECTED / head unchanged
new QR hard violation                     -> candidate REJECTED / head unchanged
first repair improves but not passes       -> DRAFT head, bounded second repair
second repair passes                       -> READY
external/loop budget insufficient          -> BUDGET_EXHAUSTED / no paid call
paid repair                                -> reserve before generate, settle actual
concurrent user branch move                -> STALE_SOURCE / user head preserved
hard LOCK_TEXT                             -> no candidate persisted
0.1 + 0.2 USD                              -> exact 0.3 via micros
2,000-node structural document             -> target repaired, all siblings retained
```

### Benchmark/eval

- 2,000-node deterministic structural repair harness;
- NODE-05 `auto-repair@1.0.0` has 8 cases;
- candidate fixes cumulative DRAFT→READY case missing in baseline;
- safety guardrails: unsafe branch overwrite, paid-without-reservation, loop-bound exceeded.

## Hosted gates

`.github/workflows/auto-repair.yml` requires six jobs: contract, quality, integration, budget, PostgreSQL CAS, benchmark.

The DB job applies `0001 + 0009 + 0010`, proves candidate insertion leaves source head unchanged, promotes a quality-approved candidate, and proves a simulated concurrent user head causes CAS failure while leaving the repair candidate DRAFT.

## Completion policy

Do not mark COMPLETE until the final release HEAD executes all required jobs green. If GitHub returns the known billing/spending annotation with runner id 0 and no steps, record it as an external validation blocker only.

Current:

```text
implementation                       IMPLEMENTED
static architecture validator        hosted execution pending
TS6 typecheck                        hosted execution pending
unit/integration tests               hosted execution pending
budget ordering tests                hosted execution pending
NODE-05 baseline/candidate gate       hosted execution pending
PostgreSQL off-head/CAS test          hosted execution pending
2k-node benchmark                    hosted execution pending
```

Overall: **IMPLEMENTED / VALIDATING / not COMPLETE**.
