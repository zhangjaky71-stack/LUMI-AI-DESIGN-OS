# NODE-73 — Final Hard-Stops Source Closure

Status: **SOURCE_IMPLEMENTED / VALIDATION_PENDING**

This record does not change NODE-73 Final Acceptance to PASS.

## Provider daily USD hard stop

Source closure now includes:

- PostgreSQL migration `0018_provider_daily_cost_hard_stop`;
- global provider/day limits using exact `numeric(20,8)` amounts;
- UTC accounting day owned by the database;
- cross-tenant provider/day advisory locking;
- committed actual + active reservation admission check;
- missing provider limit fail-closed after enforcement activation;
- actual settlement serialized against new admissions;
- actual cost inherits reservation admission day;
- runtime identity cannot mutate platform caps;
- DB hard-stop denials normalized to the existing `BudgetExceeded` contract;
- canonical `LedgerBudgetGuard(PostgresModelCostAccounting)` factory;
- production/staging `ModelGateway` refuses request-local budget fallback;
- staging/production IaC supplies `LUMI_DATABASE_URL` to model-gateway;
- static and PostgreSQL integration acceptance scripts;
- production activation/evidence runbook.

Still required before acceptance:

- regenerate the stale root `uv.lock` using canonical Python 3.12 / uv 0.11.28;
- restore GitHub Actions runner allocation;
- execute canonical frozen CI;
- apply migration to the target environment;
- configure reviewed provider caps and enable the singleton hard-stop policy;
- execute and archive concurrent production/staging evidence.

## Sandbox egress isolation

Source closure now includes:

- `sandbox-runtime.isolated_network=true` in staging and production;
- ECS compute selects isolated data subnets + dedicated sandbox SG for isolated services;
- data/isolated route tables have no NAT/Internet default route;
- sandbox SG has no `0.0.0.0/0` egress;
- private ECR API/DKR, Logs, Secrets Manager and KMS interface endpoints;
- S3 gateway endpoint on isolated route tables;
- Redis and RabbitMQ allow sandbox SG;
- PostgreSQL intentionally does not allow sandbox SG;
- Terraform validation prevents sandbox-runtime from silently returning to the ordinary network;
- static contract validator and operational acceptance runbook.

Still required before acceptance:

- `terraform fmt -check` and real plan/validate on the exact release candidate;
- apply core state first so the new sandbox SG output is available to app state;
- apply app state;
- run an in-task positive internal-dependency matrix;
- prove arbitrary public HTTPS/TCP fails;
- prove PostgreSQL access fails;
- prove undeclared S3 access fails;
- archive route table, SG, VPC endpoint, task network and CloudWatch evidence.

## Current external blockers

GitHub Actions runner allocation remains blocked by the account billing/spending-limit condition observed on prior node workflows. This must be classified as `BLOCKED_EXTERNAL`, not as a code test PASS or FAIL.

The root `uv.lock` is also stale relative to the current workspace manifest and therefore the canonical frozen install/release gate cannot yet be claimed.

## Final status

NODE-73 remains **NOT ACCEPTED** until every mandatory release item in `reports/nodes/NODE-73/release-acceptance.md` passes with evidence from the exact release candidate.
