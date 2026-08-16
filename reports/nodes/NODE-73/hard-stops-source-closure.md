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

## Production rollback drill

Source closure now includes:

- public ECS services already use canary deployment alarms with automatic `rollback=true`;
- non-public ECS services already use deployment circuit breaker rollback;
- `Deploy Production` now freezes `predeploy-ecs-state.json` before RDS snapshot, migration, or application mutation;
- the rollback source artifact contains immutable task-definition ARNs from the last verified steady state;
- `scripts/ecs-rollback-to-state.sh` validates the snapshot and all target task definitions before the first mutation;
- final acceptance refuses a no-op rollback as proof by default;
- rollback updates only changed services, waits for ECS steady state, and verifies target restoration;
- rollback evidence records `database_downgrade_attempted=false`;
- protected `Final Operational Drills` workflow binds rollback to the exact production deployment artifact and exact AWS account/role;
- public `/health/ready` must recover after rollback;
- operational runbook documents first-bootstrap limitation and mandatory Terraform reconciliation after emergency rollback.

Still required before acceptance:

- deploy at least one verified known-good production release before the final release candidate;
- execute a real release that changes at least one task definition;
- execute the protected rollback drill against the exact deployment artifact;
- archive ECS state before/after, restored task definitions, readiness recovery, operator identity and timeline;
- document source/Terraform reconciliation before normal deployment resumes.

## Alert firing and delivery

Source closure now includes:

- dedicated customer-managed KMS key for deployment alert transport;
- KMS key policy explicitly permits CloudWatch/EventBridge/SNS cryptographic use required by encrypted SNS publishing;
- encrypted SNS deployment-alert topic with account-owner administration preserved;
- encrypted SQS evidence queue and SNS subscription;
- public canary rollback alarms feed a CloudWatch composite deployment alarm with both `alarm_actions` and `ok_actions`;
- non-public ECS `SERVICE_DEPLOYMENT_FAILED` events route through EventBridge to the same topic;
- bootstrap production/staging deployment role includes CloudWatch, EventBridge, SNS, SQS and ECS permissions needed to provision and execute drills;
- `scripts/alert-delivery-drill.sh` performs a controlled synthetic `OK -> ALARM -> OK` sequence;
- the drill requires both ALARM and recovery notifications to arrive through SNS -> SQS before it can emit `passed=true`;
- the drill does not call a paid provider or intentionally break production application traffic;
- protected `Final Operational Drills` workflow binds the drill to a frozen production manifest and exact AWS account/role.

Still required before acceptance:

- apply the alert infrastructure in the real target account;
- execute the controlled alarm firing/recovery drill and archive the AWS delivery evidence;
- prove real production deployment-failure events route into the deployment alert topic;
- connect the approved human on-call destination;
- prove human delivery/acknowledgement. The SQS evidence sink proves machine transport only and is not sufficient human notification evidence.

## Current external blockers

GitHub Actions runner allocation remains blocked by the account billing/spending-limit condition observed on prior node workflows. This must be classified as `BLOCKED_EXTERNAL`, not as a code test PASS or FAIL.

The root `uv.lock` is also stale relative to the current workspace manifest and therefore the canonical frozen install/release gate cannot yet be claimed.

Real AWS Terraform plan/apply, rollback execution, sandbox egress probes, provider budget concurrency proof and alert delivery/human acknowledgement remain runtime evidence requirements.

## Final status

NODE-73 remains **NOT ACCEPTED** until every mandatory release item in `reports/nodes/NODE-73/release-acceptance.md` passes with evidence from the exact release candidate.
