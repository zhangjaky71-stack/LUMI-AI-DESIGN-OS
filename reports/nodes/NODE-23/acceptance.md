# NODE-23 Acceptance — Capability Registry V1

Status: **IMPLEMENTED / VALIDATING**

Canonical contract: `docs/models/CAPABILITY-REGISTRY-V1.md`  
Persistence mapping: `docs/models/CAPABILITY-REGISTRY-PERSISTENCE-V1.md`

## Implemented

- separated Provider / Model Definition / Model Revision / Capability Claim / Pricing Snapshot /
  Benchmark Score / Routing Profile / Organization Model Policy contracts;
- explicit capability support semantics: `full / partial / none / unknown` with evidence source,
  confidence and observation time;
- immutable versioned Registry Snapshot with checksum identity and request-time provenance pinning;
- NODE-07 seed normalization preserving five providers, 28 models, 15 routing profiles and zero
  synthetic benchmark winners;
- historical pricing normalization, expiry-aware live lookup and raw-to-normalized pricing count
  reconciliation;
- versioned benchmark evidence with dataset/run/sample/confidence/statistics fields;
- evidence-aware Routing Profile evaluator that returns `score=None` when required measurements
  are incomplete instead of inventing a primary;
- tenant Organization Model Policy with disabled provider / region / preference / data handling
  controls and monotonically increasing policy version;
- Registry-first Model Router integration with explicit `adapter_unavailable` rejection;
- route/model provenance fields for registry snapshot and model revision;
- explicit measured/unmeasured quality and latency semantics;
- in-process immutable snapshot swap / cache invalidation behavior;
- PostgreSQL migration `20260816_0007`, deterministic seed publisher and read-side snapshot loader;
- runtime SELECT-only grants for global registry facts and RLS-protected tenant policy writes;
- PostgreSQL round-trip / idempotency / checksum conflict / grant / RLS verification tooling;
- static NODE-23 architecture validator and six JSON Schema exports.

## Dedicated hosted gate

`.github/workflows/node-23-capability-registry.yml` is intended to execute with Python 3.12,
frozen workspace dependencies and PostgreSQL. It does not require any live model provider key or
public provider network call.

The gate is designed to execute:

1. Capability Registry architecture/source validator;
2. Registry, Router and Routing Profile contract tests plus NODE-22 Model Gateway regression;
3. six JSON Schema export/parse checks and exact seven-gap ledger validation;
4. Ruff and Pyright for NODE-23/affected Model Gateway scope;
5. PostgreSQL migration from `0006 -> 0007`;
6. deterministic NODE-07 registry publication and exact cardinality/pricing reconciliation;
7. PostgreSQL read-side round-trip and same-version/different-checksum failure injection;
8. global registry runtime read-only grants and organization policy RLS checks;
9. downgrade exactly to `0006`, proof that NODE-20 baseline remains, then reapply `0007` and
   rerun registry invariants.

## Required classification

Do not call this node COMPLETE until the hosted job receives a runner and actually executes the
above checks. A GitHub job with `runner_id=0`, `steps=[]` and the account payment/spending-limit
annotation is `BLOCKED_EXTERNAL`, not a source-code failure and not PASS.

No pytest/Ruff/Pyright/PostgreSQL/Alembic result is claimed merely because the implementation and
workflow exist in the repository.

## Explicit gaps

See `reports/nodes/NODE-23/gap-ledger.json`.

The durable Registry closes NODE-22 `MODEL-REGISTRY-001` at the registry/control-plane contract
and persistence level. It does **not** claim that Google, Black Forest Labs or Runway execution
adapters exist, that live LUMI benchmark winners have been measured, that broker-wide registry
invalidation or admin publish approval is composed, that asyncpg packaging is frozen, that the
NODE-22 standalone API package edge is resolved, or that externally blocked Hosted Actions
passed.

Current engineering status: `IMPLEMENTED -> VALIDATING`, with Hosted CI expected to remain
`BLOCKED_EXTERNAL` until the GitHub account condition is resolved.

Next engineering node: **NODE-24 — Provider Health**.
