# NODE-20 — Idempotency & Side Effect Gateway Acceptance

Status: **IMPLEMENTED / VALIDATING**  
Hosted status: **not PASS until a runner actually executes the workflow**

## Implemented

- canonical request hashing with recursive normalization and ephemeral trace/retry stripping;
- deterministic internal operation key generation;
- operation-type-scoped tenant idempotency identity;
- NEW / IN_PROGRESS / SUCCEEDED / FAILED_RETRYABLE / FAILED_FINAL contract;
- lease owner + expiry and stale recovery claim;
- request-hash conflict rejection with canonical 409 code;
- completed response replay without re-execution;
- request-local `Idempotent-Replayed: true` middleware signal;
- `IdempotentApiService` decorator for the five current API mutations requiring Idempotency-Key;
- paid SideEffectGateway with provider acceptance checkpoint;
- provider reconciliation for success/running/not-found/ambiguous states;
- ambiguous paid effects fail safe and never silently re-execute;
- required metric names and metric boundary;
- forward PostgreSQL migration `20260816_0006` evolving the NODE-10 ledger;
- existing Generation operation FK preserved;
- tenant RLS preserved/recreated;
- Cost Ledger operation FK plus one-charge-per-operation partial unique index;
- fail-closed downgrade if NODE-20 operation-type key scopes cannot fit NODE-10 uniqueness;
- fail-closed downgrade if a Cost Ledger row already carries NODE-20 operation lineage;
- memory concurrency/crash-window failure injection suite;
- HTTP replay/conflict contract test;
- PostgreSQL concurrent claim/RLS/stale recovery/cost-charge invariant script;
- four machine-readable JSON schemas.

## Failure-injection evidence committed

1. provider accepted request + hard process crash before local success commit;
2. provider reconciliation converges the same operation without a second paid call;
3. missing reconciliation for ambiguous paid work blocks re-execution;
4. duplicate completed request replays exactly one business result;
5. same key + different semantic request conflicts;
6. two concurrent same-key callers enter the effect once;
7. same client key in different operation types remains independent;
8. stale lease is recovered under a new lease owner;
9. duplicate Cost Ledger charge for one operation is rejected by PostgreSQL;
10. cross-tenant operation visibility is denied by RLS.

## Canonical source checks

```bash
uv sync --all-packages --frozen
PYTHONPATH=apps/api/src uv run python tools/node20/validate_idempotency.py
PYTHONPATH=apps/api/src uv run pytest -q \
  apps/api/tests/test_idempotency_gateway_contract.py \
  apps/api/tests/test_idempotency_http_contract.py
PYTHONPATH=apps/api/src uv run python tools/node20/export_idempotency_schemas.py
uv run ruff check apps/api/src/lumi_api/idempotency apps/api/src/lumi_api/api/v1/idempotency_middleware.py apps/api/tests/test_idempotency_*.py tools/node20
uv run pyright apps/api/src/lumi_api/idempotency apps/api/src/lumi_api/api/v1/idempotency_middleware.py apps/api/tests/test_idempotency_*.py tools/node20
```

Hosted workflow must additionally:

```text
start PostgreSQL
upgrade through NODE-19 / 0005
load deterministic two-tenant fixture
upgrade to 0006
run baseline NODE-10 invariants at current head
run NODE-20 core PostgreSQL concurrency/RLS/stale-lease invariants without writing Cost Ledger fixtures
downgrade to 0005
verify NODE-19 survives and NODE-20 columns/indexes are removed
reapply 0006
run full NODE-20 invariants, including append-only one-charge-per-operation fencing
```

The ordering is intentional. `cost_ledger` has been immutable since NODE-10. NODE-20 also
refuses to downgrade when an existing Cost Ledger row contains `operation_id`, because
removing that column would destroy audit lineage. The workflow therefore proves structural
downgrade before creating its immutable Cost test evidence, then performs the Cost fence only
after the final reapply. It never disables the immutable trigger or deletes a charge to make a
downgrade pass.

## Evidence required before COMPLETE

- Python 3.12 frozen install green;
- source/failure-injection tests green;
- architecture validator green;
- four JSON schemas parse green;
- Ruff green;
- Pyright green;
- real PostgreSQL migration/concurrency/RLS/charge fencing green;
- safe downgrade/reapply green before immutable Cost lineage exists;
- repository CI/security green;
- stacked NODE-09 through NODE-19 dependencies resolved.

## Explicit non-claims

- no distributed exactly-once claim;
- no claim that provider-native reconciliation exists before provider adapters land;
- no claim that expired rows are safe to physically delete;
- no claim that a production database with NODE-20 Cost Ledger operation lineage can be losslessly downgraded to NODE-19;
- no production paid-provider PASS;
- no hosted PASS from a workflow that never received a runner.

## Completion rule

A GitHub job with `runner_id=0` and `steps=[]` is `BLOCKED_EXTERNAL`, not a source failure and not a PASS.

Next: **NODE-21 — Sandbox Runtime**.
