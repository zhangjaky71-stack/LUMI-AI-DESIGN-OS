# Release Closure P0 Evidence

Date: 2026-08-18
Branch: `release-closure-p0`
Base: `node-73-final-acceptance-release`
Scope: close code-addressable P0 blockers identified by NODE-73 Final Acceptance without inventing a new NODE.

## Executive status

`release-closure-p0` is **not Final Acceptance / not Production GO-LIVE approval**.

This branch closes two code/IaC gaps that NODE-73 correctly left open:

1. platform-wide provider-dollar hard-stop implementation; and
2. explicit Production/Staging Sandbox egress isolation in shared IaC.

It does **not** manufacture live evidence. PostgreSQL migration execution, Terraform plan/apply, real sandbox egress probes, hosted RC evidence, six-runtime image promotion, GitHub-hosted CI recovery, and the root `uv.lock` freshness gate remain required before NODE-73 may be marked accepted.

## P0-1 — platform-wide Provider USD/day hard stop

Status: **IMPLEMENTED IN CODE / LIVE DATABASE PROOF PENDING**

### Implemented

- Added `db/migrations/0015_provider_cost_guard.sql`.
- Added canonical `provider_cost_guard_policy` with default platform policy:
  - currency: USD;
  - daily cap: `$100.00000000`;
  - enabled: true;
  - fail-closed: true.
- Added one `provider_cost_daily_usage` row per UTC day as the cross-process serialization point.
- Added durable reservation records with organization / operation / project / task / agent-run / generation attribution.
- Added append-only `provider_cost_ledger` with mutation-rejection trigger.
- Added atomic `provider_cost_reserve`, `provider_cost_commit`, and `provider_cost_release` functions.
- Reservation uses a row lock before any paid provider call can proceed through `LedgerBudgetGuard`.
- Added idempotency collision detection.
- Added fail-closed normalization for policy missing/disabled/accounting unavailable conditions.
- Added `0016_provider_cost_guard_snapshot_fix.sql` so the cap captured in the UTC-day usage row remains authoritative for that day; mid-day policy edits cannot silently change an open day's boundary.
- Actual provider cost may exceed an estimate after the provider has already accepted work; that unavoidable sunk-cost overshoot is recorded via `breached_at`, and subsequent reservations are blocked by the daily boundary.
- Added `PostgresCostAccounting` adapter and unit coverage.
- Added `build_environment_budget_guard()` composition contract:
  - `staging` and `production` require durable PostgreSQL accounting;
  - missing connection raises `COST_GUARD_DURABLE_ACCOUNTING_REQUIRED`;
  - hosted execution cannot silently fall back to `RequestBudgetGuard`.

### Tests added

- `services/model-gateway/tests/test_postgres_cost_accounting.py`
- `services/model-gateway/tests/test_production_cost_guard.py`
- provider-cost invariants in `evals/tests/test_release_security_contracts.py`

### Still required for acceptance

- apply migrations `0015` and `0016` to a disposable PostgreSQL instance and then Production-like Staging;
- run concurrent reservation tests against real PostgreSQL and prove aggregate reservations cannot cross the daily cap;
- prove the deployed Model Gateway bootstrap provides the durable accounting connection;
- record real provider requests before/at/after the cap boundary;
- archive ledger and alert evidence.

## P0-2 — Production Sandbox egress isolation

Status: **IMPLEMENTED IN IAC / TERRAFORM APPLY + LIVE PROBE PENDING**

### Existing inner boundary retained

`sandbox-runtime` already executes child Docker work with `--network none`; this branch does not weaken or duplicate that inner sandbox boundary.

### IaC changes

- Converted the shared `app` Security Group into application identity/ingress only; it no longer grants Internet egress.
- Added `app_internet_egress` Security Group for non-sandbox services that legitimately need provider/webhook Internet access.
- Added `sandbox_egress` Security Group that allows only:
  - private VPC CIDR traffic for internal control-plane dependencies; and
  - TCP/443 to the AWS-managed S3 prefix list for approved asset transport.
- `sandbox_egress` contains no `0.0.0.0/0` rule.
- Added PrivateLink interface endpoints for `ecr.api`, `ecr.dkr`, `logs`, and `secretsmanager` so Fargate execution dependencies do not require arbitrary public NAT access.
- ECS service composition now selects Security Groups by service name:
  - `sandbox-runtime` -> app identity + restricted sandbox egress;
  - all other services -> app identity + explicit Internet egress.
- Compute module validation requires the `sandbox-runtime` deployment unit so the restricted branch cannot disappear silently.
- Propagated the same topology through both Staging and Production core/app modules.

### Tests added

`evals/tests/test_release_security_contracts.py` asserts:

- Sandbox is special-cased to the restricted Security Group;
- app identity does not contain public egress;
- only the non-sandbox Internet egress group contains `0.0.0.0/0`;
- sandbox egress contains VPC + S3 only;
- required PrivateLink endpoints exist;
- Staging and Production propagate the restricted Security Group IDs;
- the inner runtime still contains `--network none`.

### Still required for acceptance

- run `terraform fmt -check`, `terraform validate`, and Production-like Staging `terraform plan` with the actual AWS provider/version lock;
- apply to Production-like Staging;
- launch the real `sandbox-runtime` task image;
- prove approved Redis/RabbitMQ/S3/control-plane traffic remains functional;
- prove arbitrary public DNS/IP HTTPS and raw TCP egress are denied;
- prove ECR image pull, CloudWatch Logs, and Secrets Manager remain functional through private endpoints;
- archive VPC Flow Logs / task probe output as release evidence.

## P0-3 — canonical root `uv.lock`

Status: **NOT CLOSED**

Root `pyproject.toml` currently declares these workspace packages that are absent from the lock manifest:

- `lumi-auth`;
- `lumi-domain`;
- `lumi-project-core`;
- `lumi-asset-storage`.

The first three have no base third-party dependencies. `lumi-asset-storage` also has no base dependency, but declares optional `s3 = ["boto3>=1.42,<2"]`. The current lock contains neither the workspace member nor the boto3 dependency graph.

Therefore a manifest-only hand edit would be a false fix. The canonical gate remains:

```bash
uv lock
uv sync --frozen
```

using Python 3.12 and normal registry access, followed by the full Python gate. The current execution environment cannot resolve missing registry metadata and does not contain a Python 3.12 interpreter, so this branch intentionally does not claim lock freshness.

## External/live blockers unchanged

The following NODE-73 blockers are outside this branch's code-only proof boundary and remain open until real evidence exists:

- GitHub Actions account/billing/spending-limit block preventing hosted runner execution;
- NODE-68/69/70/71/72 Production-like Staging / cloud evidence gaps;
- real six-runtime image promotion and transport proof;
- passed Production-like Staging RC package;
- final Production evidence package and rollback/DR proof.

## Release decision

Current decision: **KEEP NODE-73 FINAL ACCEPTANCE BLOCKED**.

Merge this branch only as the code/IaC remediation layer. Do not change the Final Acceptance verdict until all remaining live gates above produce auditable evidence.
