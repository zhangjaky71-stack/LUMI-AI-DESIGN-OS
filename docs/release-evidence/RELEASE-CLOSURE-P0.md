# Release Closure P0 Evidence

Date: 2026-08-18
Branch: `release-closure-p0`
Base: `node-73-final-acceptance-release`
Draft PR: `#135`
Scope: close code-addressable P0 blockers identified by NODE-73 Final Acceptance without inventing a new NODE.

## Executive status

`release-closure-p0` is **not Final Acceptance and not Production GO-LIVE approval**.

This branch implements code/IaC remediation for the code-addressable parts of the NODE-73 blockers:

1. one platform-wide Provider USD hard stop, enforced before paid Model Gateway calls;
2. explicit Production/Staging Sandbox egress isolation;
3. release-contract hardening so NODE-71 freezes the exact six immutable RC images and their provenance, NODE-72 must deploy those exact digests, and the Production first-day Provider limit cannot exceed `$100`.

NODE-73 remains blocked because live evidence is still missing. Real PostgreSQL execution, Terraform plan/apply, Sandbox egress probes, a real six-runtime build/provenance pipeline, Production-like Staging RC evidence, canonical `uv.lock` freshness, and final Production/rollback/DR evidence are still required.

## P0-1 — platform-wide Provider USD/day hard stop

Status: **IMPLEMENTED IN CODE / LIVE POSTGRESQL + DEPLOYED IMAGE PROOF PENDING**

### Canonical accounting architecture

Release Closure reuses NODE-27's existing financial truth and does **not** create a second Provider ledger.

Canonical facts remain:

- `cost_ledger` — append-only actual Provider cost / adjustment / reversal facts;
- `cost_reservations` — pre-Provider estimated-cost occupancy;
- existing NODE-27 usage, quota and reconciliation tables/runtime.

Early Release Closure drafts that introduced parallel `provider_cost_*` tables/functions were removed. The final branch extends the existing NODE-27 boundary only.

### Platform policy

Added Alembic revision:

- `apps/api/alembic/versions/0018_platform_provider_cost_guard.py`

It creates singleton `platform_provider_cost_guard` with:

- `policy_key = 'platform'`;
- USD/UTC-day semantics;
- default cap `$100.00000000`;
- `enabled = true`;
- `fail_closed = true`;
- database constraint `daily_cap_usd > 0 AND daily_cap_usd <= 100.00000000`.

The `$100` ceiling is therefore a schema maximum, not merely a default. `lumi_app` has SELECT-only access and cannot raise, disable or delete the policy at runtime.

The policy is mapped into SQLAlchemy metadata through `PlatformProviderCostGuard`, so the normal ORM schema-drift gate can validate it after migration.

### Cross-process / cross-organization hard stop

`PlatformGuardedCostGateway` wraps the canonical `PostgresCostGateway`.

Before a paid reservation it:

1. obtains PostgreSQL advisory transaction lock `cost-budget:platform:provider-usd:utc-day`;
2. reads the fail-closed singleton policy;
3. calculates current UTC-day Provider spend from canonical `cost_ledger` across all organizations;
4. calculates active USD reservations from canonical `cost_reservations` across all organizations;
5. rejects when `spent + active + requested > cap`;
6. while still holding the platform lock, delegates to NODE-27's canonical `PostgresCostGateway.reserve()`.

Commit/release are serialized against the same platform lock. If a Provider has already accepted work and actual cost exceeds the estimate, the sunk fact is committed rather than hidden; later reservations then fail closed.

### Model Gateway binding

`PostgresModelCostAccounting` now uses `PlatformGuardedCostGateway`. The `lumi_model_gateway` package itself remains database-neutral behind `CostAccountingPort`.

Hosted composition root:

- `apps/api/src/lumi_api/model_gateway_runtime.py`

`build_hosted_model_gateway()` fixes the Hosted financial path to:

`LedgerBudgetGuard(PostgresModelCostAccounting(database_dsn))`

The function does not accept an injectable `budget_guard`, so Hosted composition cannot silently fall back to request-local budgeting.

`lumi-api` now explicitly declares `lumi-model-gateway` as a workspace dependency. The checked-in lock is intentionally not hand-edited; the dependency must be captured by canonical `uv lock` regeneration.

### Provider credential boundary

Staging and Production IaC now make `model-gateway` the only deployment unit holding Provider credentials:

- `agent-runtime` no longer receives `LUMI_MODEL_PROVIDER_SECRET`;
- `worker-media` no longer receives `LUMI_MEDIA_PROVIDER_SECRET`;
- `model-gateway` receives `LUMI_MODEL_PROVIDER_SECRET` and `LUMI_MEDIA_PROVIDER_SECRET`;
- `model-gateway` receives `LUMI_DATABASE_URL` for durable NODE-27 accounting.

`validate_production_iac_contract.py` and `evals/tests/test_release_security_contracts.py` enforce this least-privilege topology in both Staging and Production.

### PostgreSQL acceptance

Added `scripts/integration_platform_provider_cost_guard.py` and wired it into the existing NODE-27 `cost-ledger.yml` workflow.

It is designed to prove on real PostgreSQL that:

- even the migration/admin role cannot set the hard ceiling above `$100`;
- a temporary test cap is derived from observed baseline + `$0.30` and cannot exceed `$100`;
- six concurrent `$0.10` reservations split across two organizations compete on one platform lock;
- exactly three succeed under `$0.30` incremental headroom;
- disabled policy fails closed;
- actual `$0.25` Provider cost may commit for an already accepted `$0.10` reservation;
- post-overshoot reservations are denied;
- runtime role cannot mutate the platform policy.

The NODE-27 static contract also validates the migration, ORM mapping, canonical wrapper, hosted composition root, workspace dependency and integration markers.

### Production release limit alignment

A pre-existing release-contract conflict was found and corrected: `production/deployment/manifest-template.json` had `daily_provider_spend_usd: 250` while the new durable hard ceiling is `$100`.

Release Closure now enforces the same boundary at release time:

- Production manifest template default is `100`;
- `production-deployment-gate.py` requires `0 < daily_provider_spend_usd <= 100`;
- `validate_production_deployment_contract.py` includes a `$100.01` negative drill that must BLOCK.

The deployment manifest can therefore choose a stricter value below `$100`, but cannot advertise or authorize a higher first-day Provider envelope than the durable database boundary.

## P0-2 — Production Sandbox egress isolation

Status: **IMPLEMENTED IN IAC / TERRAFORM APPLY + LIVE PROBE PENDING**

### Existing inner boundary retained

`sandbox-runtime` already executes child Docker work with `--network none`; Release Closure keeps that inner deny-all execution boundary.

### Shared IaC boundary

- shared `app` Security Group is identity/ingress only and grants no public egress;
- `app_internet_egress` grants explicit Internet egress to non-Sandbox services;
- `sandbox_egress` allows only private VPC traffic plus TCP/443 to the AWS-managed S3 prefix list;
- `sandbox_egress` contains no `0.0.0.0/0` rule;
- PrivateLink interface endpoints exist for `ecr.api`, `ecr.dkr`, `logs`, and `secretsmanager`;
- ECS composition attaches:
  - `sandbox-runtime` -> app identity + restricted Sandbox egress;
  - other services -> app identity + explicit Internet egress;
- compute module requires the `sandbox-runtime` deployment unit;
- Staging and Production use the same topology.

Static IaC/release-security tests encode these invariants so a later change cannot silently reattach public egress to Sandbox.

### Still required for acceptance

- run `terraform fmt -check`, `terraform validate`, and Production-like Staging `terraform plan` with the pinned provider;
- apply to Production-like Staging;
- launch the real `sandbox-runtime` image;
- prove Redis/RabbitMQ/S3/internal control-plane traffic remains functional;
- prove arbitrary public DNS/IP HTTPS and raw TCP egress are denied;
- prove ECR pull, CloudWatch Logs and Secrets Manager work through PrivateLink;
- archive VPC Flow Logs and task probe output.

## P0-3 — canonical root `uv.lock`

Status: **NOT CLOSED**

The workspace/dependency graph has evolved beyond the checked-in lock. Previously identified missing workspace entries include:

- `lumi-auth`;
- `lumi-domain`;
- `lumi-project-core`;
- `lumi-asset-storage`.

`lumi-asset-storage` also declares optional `s3 = ["boto3>=1.42,<2"]`, whose dependency graph is absent from the current lock. Release Closure additionally makes the already-present workspace package `lumi-model-gateway` an explicit dependency of `lumi-api`.

A manifest-only manual edit would be a false fix. The canonical repair remains:

```bash
uv lock
uv sync --all-packages --frozen
```

using Python 3.12 and normal registry access, followed by Ruff, Pyright, pytest and the NODE-27 PostgreSQL acceptance suite.

The canonical lock command is now consistent in the Cost Ledger, NODE-71 Staging Acceptance and Final Product Acceptance workflows: all use `--all-packages --frozen` where the full workspace is being accepted.

## P0-4 — exact RC image identity and provenance

Status: **GATES IMPLEMENTED / REAL SIX-IMAGE BUILD + ENTRYPOINT EVIDENCE PENDING**

### NODE-71 now freezes the real image set

`staging/acceptance/evidence-template.json` now requires, for all six runtime units:

- immutable `@sha256` image digest;
- source `git_sha`;
- build recipe reference;
- executable entrypoint;
- SBOM reference;
- provenance reference;
- source-path list.

`staging-acceptance-gate.py` validates exactly six image/provenance entries and freezes the normalized `container_image_set` into the NODE-71 decision hash.

For `model-gateway`, provenance must explicitly include:

- `services/model-gateway`;
- `apps/api/src/lumi_api/model_gateway_runtime.py`;
- `apps/api/src/lumi_api/costs/model_gateway_adapter.py`.

Therefore a Model Gateway image that omits the Hosted durable-cost composition cannot receive NODE-71 PASS merely because its Git SHA matches.

`validate_staging_acceptance_contract.py` contains negative drills for mutable images, provenance SHA swaps and missing Model Gateway Hosted source paths. `ENV-01` and `PARITY-IMAGE` were updated to make digest/provenance/SBOM/entrypoint evidence a P0 requirement.

### NODE-72 cannot swap images after Staging acceptance

`production-deployment-gate.py` now requires:

`production manifest.images == NODE-71 decision.container_image_set.images`

as an exact dictionary equality check. A different but syntactically valid `@sha256` digest is rejected.

`validate_production_deployment_contract.py` includes a negative drill that swaps only the Model Gateway digest to another valid digest and requires BLOCK.

Final Acceptance already contains P0 `PROD-02`: exact Staging-accepted immutable digests must be deployed through the controlled Production workflow and canary. Final Gate freezes both NODE-71 and NODE-72 decisions and the Production deployment manifest; no additional third copy of the same digest-comparison algorithm was added.

### Real image build remains unresolved

Repository inspection confirms the important remaining gap:

- Production deployment workflow consumes prebuilt immutable digests; it does not build six images;
- Staging infrastructure workflow also consumes provided digests;
- `model-gateway.yml` runs Python contracts/tests but does not build a container;
- no six-runtime build/promotion pipeline was found;
- `services/model-gateway/src/lumi_model_gateway` currently has no standalone `cli.py` or `server.py` proving an independently executable network-service entrypoint.

This is intentionally **not** marked fixed. NODE-71 now blocks until the real `model-gateway` image has an auditable build recipe, executable entrypoint, SBOM/provenance, immutable digest, and the required Hosted composition sources.

## Hosted CI evidence status

GitHub Actions runs are created for PR #135, but sampled critical jobs fail **before executing any step**:

- Cost Ledger `cost-contract`: failure with empty steps; dependent jobs skipped;
- Production IaC Contract source/Terraform jobs: failure with empty steps;
- Final Product Acceptance source/canonical-lock jobs: failure with empty steps.

No checkout, Python, Terraform, `uv`, test or application command ran in those sampled jobs, and job logs were unavailable. These red runs are therefore not application-test failures; they are consistent with the existing GitHub-hosted runner/account/billing/spending-limit blocker.

## Remaining live blockers

Before NODE-73 can change from BLOCKED, auditable PASS evidence is still required for:

- GitHub-hosted runner execution recovery or equivalent trusted CI;
- canonical `uv lock` + `uv sync --all-packages --frozen`;
- Alembic `0018` and the cross-organization Provider-cost acceptance on real PostgreSQL;
- Terraform format/validate/plan/apply in Production-like Staging;
- live Sandbox egress allow/deny probes;
- a real six-runtime image build/promotion process;
- a real independently executable `model-gateway` image/entrypoint carrying the Hosted composition root;
- SBOM/provenance and exact digest capture for all six runtime images;
- NODE-68/69/70/71/72 cloud/RC evidence;
- Production smoke/canary/rollback and DR evidence;
- final operational approvals/handoff.

## Release decision

Current decision: **KEEP NODE-73 FINAL ACCEPTANCE BLOCKED**.

PR #135 remains a Draft remediation layer. Do not mark it as Final Acceptance, do not declare Production GO-LIVE, and do not change the NODE-73 verdict until all remaining lock, CI, PostgreSQL, Terraform, Staging, image-build/provenance, Production and DR gates are auditable and passed.
