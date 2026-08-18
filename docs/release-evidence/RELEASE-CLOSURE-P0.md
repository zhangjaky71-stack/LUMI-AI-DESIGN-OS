# Release Closure P0 Evidence

Date: 2026-08-18
Branch: `release-closure-p0`
Base: `node-73-final-acceptance-release`
Draft PR: `#135`
Scope: close code-addressable P0 blockers identified by NODE-73 Final Acceptance without inventing a new NODE.

## Executive status

`release-closure-p0` is **not Final Acceptance and not Production GO-LIVE approval**.

This branch implements the code/IaC remediation for two NODE-73 P0 gaps:

1. one platform-wide Provider USD hard stop, enforced before paid Model Gateway calls; and
2. explicit Production/Staging Sandbox egress isolation.

The branch deliberately keeps NODE-73 blocked because live evidence is still missing. In particular, real PostgreSQL execution, Terraform plan/apply, sandbox egress probes, six-runtime image promotion, Production-like Staging RC evidence, root `uv.lock` freshness, and final Production/rollback/DR evidence remain required.

## P0-1 — platform-wide Provider USD/day hard stop

Status: **IMPLEMENTED IN CODE / LIVE POSTGRESQL + DEPLOYED IMAGE PROOF PENDING**

### Canonical accounting architecture

The remediation reuses NODE-27's existing financial truth. It does **not** create a second Provider ledger.

Canonical facts remain:

- `cost_ledger` — append-only actual provider cost / adjustment / reversal facts;
- `cost_reservations` — pre-provider estimated-cost occupancy;
- existing NODE-27 usage, quota and reconciliation tables and runtime.

Early Release Closure drafts that introduced parallel `provider_cost_*` tables/functions were removed from the branch. The final design extends the existing NODE-27 boundary only.

### Platform policy

Added Alembic revision:

- `apps/api/alembic/versions/0018_platform_provider_cost_guard.py`

It creates the singleton `platform_provider_cost_guard` policy with:

- `policy_key = 'platform'`;
- USD/UTC-day semantics in metadata;
- default cap `$100.00000000`;
- `enabled = true`;
- `fail_closed = true`;
- database constraint `daily_cap_usd > 0 AND daily_cap_usd <= 100.00000000`.

The `$100` ceiling is therefore a schema-level maximum, not only a default configuration value. `lumi_app` has SELECT-only access to the policy and cannot raise, disable or delete it at runtime.

The table is mapped into SQLAlchemy metadata through `PlatformProviderCostGuard`, so the normal ORM schema-drift gate can validate it after migration.

### Cross-process / cross-organization hard stop

Added `PlatformGuardedCostGateway`, a wrapper around the canonical `PostgresCostGateway`.

Before a paid reservation it:

1. obtains PostgreSQL advisory transaction lock `cost-budget:platform:provider-usd:utc-day`;
2. reads the fail-closed singleton policy;
3. calculates current UTC-day Provider spend from canonical `cost_ledger` across all organizations;
4. calculates active USD reservations from canonical `cost_reservations` across all organizations;
5. rejects when `spent + active + requested > cap`;
6. while still holding the platform lock, delegates to NODE-27's canonical `PostgresCostGateway.reserve()`.

Commit/release are also serialized against this platform lock. If the Provider has already accepted work and actual cost exceeds the estimate, the sunk financial fact is committed rather than hidden; subsequent reservations then fail closed.

### Model Gateway binding

`PostgresModelCostAccounting` now uses `PlatformGuardedCostGateway` internally. Model Gateway itself remains database-neutral through `CostAccountingPort`.

Added hosted composition root:

- `apps/api/src/lumi_api/model_gateway_runtime.py`

`build_hosted_model_gateway()` fixes the Hosted budget path to:

`LedgerBudgetGuard(PostgresModelCostAccounting(database_dsn))`

The function does not accept an injectable `budget_guard`, so Staging/Production composition cannot silently fall back to request-local budgeting.

`lumi-api` now declares the `lumi-model-gateway` workspace dependency explicitly. This dependency change is intentionally left for the canonical `uv lock` regeneration described under P0-3; the lock file is not hand-edited.

### Provider credential boundary

Staging and Production IaC were tightened so Provider credentials exist only in the `model-gateway` deployment unit:

- `agent-runtime` no longer receives `LUMI_MODEL_PROVIDER_SECRET`;
- `worker-media` no longer receives `LUMI_MEDIA_PROVIDER_SECRET`;
- `model-gateway` receives `LUMI_MODEL_PROVIDER_SECRET` and `LUMI_MEDIA_PROVIDER_SECRET`;
- `model-gateway` now also receives `LUMI_DATABASE_URL` for durable NODE-27 accounting.

`validate_production_iac_contract.py` enforces this least-privilege topology for both Staging and Production.

Deep Agent runtime already requires its resolved model to carry the NODE-22 Model Gateway trust marker, and the NODE-22 architecture validator scans caller roots for direct Provider SDK imports / raw Provider credential names. Release Closure therefore removes the deployment-level credential bypass in addition to retaining those code-level boundaries.

### PostgreSQL acceptance added

Added:

- `scripts/integration_platform_provider_cost_guard.py`

The acceptance test is wired into the existing NODE-27 `cost-ledger.yml` workflow. It is designed to prove on real PostgreSQL that:

- even the migration/admin role cannot set the cap above `$100` (`CheckViolationError` expected);
- a temporary test cap is derived from observed baseline + `$0.30`, and the test aborts if that would exceed `$100`;
- six concurrent `$0.10` reservations split across two organizations compete on one platform lock;
- exactly three reservations succeed under the `$0.30` incremental headroom;
- disabling the singleton policy causes fail-closed budget denial;
- actual `$0.25` cost can be committed for a previously reserved `$0.10` accepted operation;
- post-overshoot reservations are denied;
- the runtime role cannot mutate the platform policy.

The NODE-27 static contract now also verifies the migration, ORM mapping, canonical wrapper, hosted composition root, workspace dependency and integration markers.

### Hosted CI evidence status

GitHub Actions runs are being created for PR #135, but sampled critical jobs fail **before executing any step**:

- Cost Ledger: `cost-contract` -> failure with an empty steps list; dependent jobs skipped;
- Production IaC Contract: source/Terraform jobs -> failure with empty steps lists;
- Final Product Acceptance Gate: source/canonical-lock jobs -> failure with empty steps lists.

No checkout, Python, Terraform, `uv`, test or application command ran in those jobs, and job logs were unavailable. These red runs therefore do not constitute code/test failures; they are consistent with the existing GitHub-hosted runner/account/billing/spending-limit execution blocker.

### Still required for acceptance

- restore hosted runner execution or run an equivalent trusted CI environment;
- apply Alembic revision `0018` to disposable PostgreSQL and Production-like Staging;
- execute the new cross-organization PostgreSQL acceptance to PASS;
- build/promote the actual Model Gateway image from the hosted composition root;
- prove the deployed task receives the durable DB credential and Provider credentials while Agent Runtime/Worker Media do not;
- record real Provider calls immediately below/at/above the platform boundary;
- archive canonical ledger/reservation evidence and cost alerts.

## P0-2 — Production Sandbox egress isolation

Status: **IMPLEMENTED IN IAC / TERRAFORM APPLY + LIVE PROBE PENDING**

### Existing inner boundary retained

`sandbox-runtime` already executes child Docker work with `--network none`. Release Closure keeps that inner deny-all execution boundary.

### Shared IaC boundary

- the shared `app` Security Group is now identity/ingress only and grants no public egress;
- `app_internet_egress` provides explicit Internet egress to non-sandbox services;
- `sandbox_egress` allows only private VPC traffic plus TCP/443 to the AWS-managed S3 prefix list;
- `sandbox_egress` contains no `0.0.0.0/0` rule;
- PrivateLink interface endpoints were added for `ecr.api`, `ecr.dkr`, `logs`, and `secretsmanager`;
- ECS composition attaches:
  - `sandbox-runtime` -> app identity + restricted sandbox egress;
  - other services -> app identity + explicit Internet egress;
- the compute module requires the `sandbox-runtime` deployment unit;
- Staging and Production use the same topology.

`validate_production_iac_contract.py` and `evals/tests/test_release_security_contracts.py` encode these invariants so a later change cannot silently reattach public egress to Sandbox.

### Still required for acceptance

- run `terraform fmt -check`, `terraform validate`, and Production-like Staging `terraform plan` with the pinned provider;
- apply the IaC to Production-like Staging;
- launch the real `sandbox-runtime` image;
- prove Redis/RabbitMQ/S3/internal control-plane traffic remains functional;
- prove arbitrary public DNS/IP HTTPS and raw TCP egress are denied;
- prove ECR pull, CloudWatch Logs and Secrets Manager function through PrivateLink;
- archive VPC Flow Logs and task probe output.

## P0-3 — canonical root `uv.lock`

Status: **NOT CLOSED**

The root workspace and dependency graph have evolved beyond the checked-in lock. Previously identified missing workspace entries include:

- `lumi-auth`;
- `lumi-domain`;
- `lumi-project-core`;
- `lumi-asset-storage`.

`lumi-asset-storage` also declares optional `s3 = ["boto3>=1.42,<2"]`, whose dependency graph is absent from the current lock. Release Closure additionally makes the already-present workspace package `lumi-model-gateway` an explicit dependency of `lumi-api`, which must also be captured by the regenerated lock.

A manifest-only manual edit would be a false fix. The canonical gate remains:

```bash
uv lock
uv sync --all-packages --frozen
```

using Python 3.12 and normal registry access, followed by Ruff, Pyright, pytest and the NODE-27 PostgreSQL acceptance suite.

Until that completes successfully, P0-3 remains open.

## External/live blockers unchanged

The following NODE-73 blockers remain outside code-only proof and must produce real evidence:

- GitHub-hosted runner/account/billing/spending-limit execution recovery;
- NODE-68/69/70/71/72 Production-like Staging / cloud evidence;
- real six-runtime image build/promotion/transport proof;
- passed Production-like Staging RC package;
- final Production evidence package, rollback proof and DR proof.

## Release decision

Current decision: **KEEP NODE-73 FINAL ACCEPTANCE BLOCKED**.

PR #135 may serve as the code/IaC remediation layer only. Do not change the NODE-73 verdict until the remaining lock, hosted-CI, PostgreSQL, Terraform, Staging, image-promotion and Production evidence gates are auditable and passed.
