# NODE-20 Acceptance — Idempotency & Side Effect Gateway

Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**

## Scope delivered

- [x] Existing `idempotency_operations` is upgraded instead of creating a competing state source.
- [x] Identity is unique by `(organization_id, operation_type, idempotency_key)`.
- [x] Canonical semantic request hash rejects same-key/different-request reuse.
- [x] Lease ownership prevents concurrent equivalent execution.
- [x] Completed operations replay business result without executing again.
- [x] Provider request binding creates a crash-window recovery point.
- [x] Expired provider-bound operations require reconciliation before another execution.
- [x] Unknown provider state becomes `ambiguous` rather than silently retrying paid work.
- [x] Paid/critical side-effect policy and compensation classes are explicit.
- [x] Cost Ledger entries bind to operation ID and dedupe `(operation_id, entry_type)`.
- [x] HTTP replay header adapter is defined.
- [x] NODE-19 global Celery late ACK remains disabled until concrete cost-bearing tasks are gateway-backed.
- [x] Static contract, unit tests, DB concurrency/failure injection, and migration smoke gates are authored.

## Validation available in this implementation session

- [x] NODE-20 code and acceptance gates authored as one stacked change set.
- [x] Repository branch lineage starts exactly from NODE-19 commit `9dade666e4995deff35623dbbdf8621faa432f70`.
- [ ] Full local checkout validation unavailable because the execution environment cannot resolve `github.com`.
- [ ] Hosted GitHub Actions execution unavailable until the repository account billing/spending-limit blocker is cleared.

## Required green evidence before COMPLETE

- [ ] frozen `uv sync --all-packages --frozen`;
- [ ] Ruff and targeted Pyright;
- [ ] targeted idempotency unit tests;
- [ ] Alembic `0009` upgrade + ORM schema drift check;
- [ ] concurrent same-key test yields exactly one `EXECUTE`;
- [ ] completed duplicate replays with zero additional side-effect invocation;
- [ ] same-key/different-request returns conflict;
- [ ] provider-success/local-crash window reconciles without a second provider call;
- [ ] unknown provider state blocks a retry and records ambiguity;
- [ ] duplicate Cost Ledger charge produces one row;
- [ ] migration downgrade/upgrade smoke.

## Decision

NODE-20 may be opened as a stacked Draft PR once the implementation commit is finalized. It remains **not COMPLETE** until the hosted/integration gates execute green.

Next node: NODE-21 — Sandbox Runtime.
