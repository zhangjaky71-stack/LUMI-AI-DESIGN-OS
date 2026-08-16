# NODE-73 — Final Hard-Stops Source Closure

Status: **SOURCE_IMPLEMENTED / VALIDATION_PENDING**

This record does not change NODE-73 Final Acceptance to PASS. The canonical decision ledger is `reports/nodes/NODE-73/release-acceptance.md`.

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

## Stripe production billing and live purchase

Source closure now includes:

- real Stripe HTTP adapter without adding a new Python package dependency to the already-stale workspace lock;
- production/test secret-key mode separation and production live-mode enforcement;
- Stripe API version pinned by source and enforced on accepted webhook events;
- server-owned recurring Stripe Price IDs mapped from immutable LUMI plan versions;
- startup Price reconciliation for active/live mode, USD amount, recurrence interval/count, billing scheme and licensed usage type;
- authenticated `/api/v1/billing` runtime installed in the production/staging API;
- `PrincipalResolver` session/API-token authorization and `billing.read`/`billing.manage` permissions;
- cookie billing writes require both a valid CSRF token and an explicit allowlisted `Origin`;
- production/staging refuses Stripe Billing startup without an explicit origin allowlist or required Stripe configuration;
- Checkout accepts a plan-version identity only; amount, currency and Stripe Price remain server-owned;
- Checkout requires `Idempotency-Key` and derives a bounded hashed Stripe idempotency key for retry-safe session creation;
- first Stripe Customer creation is protected by a per-organization PostgreSQL advisory lock plus stable Stripe customer idempotency;
- raw-body `Stripe-Signature` verification with multiple `v1` signatures and a bounded replay window;
- webhook `livemode` and pinned API-version fail-closed checks;
- migration `0019_stripe_billing_runtime` with durable account/subscription/payment-event/invoice/credit state;
- payment event uniqueness on `(provider, provider_event_id)` and payload-hash collision rejection;
- payment-event claim, subscription/invoice mutation and credit grant occur within one PostgreSQL transaction;
- credit grants are idempotent and the credit/event ledgers are immutable after insert;
- tenant billing tables use forced RLS and least-privilege `lumi_app` DML grants;
- Billing ORM metadata exists so `alembic check` can detect drift rather than treating billing tables as intentional unmanaged schema;
- production/staging Terraform declares dedicated Stripe secret-key/webhook-secret resources and injects server-owned plan catalog/return URLs into API ECS;
- PostgreSQL acceptance script covers Price preflight, concurrent first Checkout, retry-safe Checkout, webhook replay, event-ID collision, one-time credit grant, RLS and table privileges;
- `docs/operations/STRIPE-LIVE-PURCHASE-DRILL.md` defines the required real-payment drill;
- `scripts/verify_stripe_live_purchase_db.py` provides a read-only production DB verifier for the exact live `sub_`, `in_` and `evt_` correlation identifiers.

Still required before acceptance:

- run static/lint/type/unit/PostgreSQL acceptance on an allocated CI runner;
- run `alembic check` and migration downgrade/upgrade smoke on the exact candidate;
- run Terraform format/validate/plan and apply the Stripe secret inventory/API task-definition changes;
- populate reviewed production live Stripe secret key and production webhook signing secret;
- configure the production Stripe webhook/event destination for the required subscription/invoice events using the source-supported API version;
- populate the approved live Price catalog and prove startup Price reconciliation passes;
- obtain finance/operator approval for one bounded real production charge;
- complete one real Stripe-hosted live purchase;
- prove live signed webhook delivery, ACTIVE subscription, PAID exact-amount invoice and exactly one credit grant;
- resend the exact paid-invoice event and prove duplicate semantics with no second credit grant;
- archive the redacted live-purchase evidence manifest and DB verifier output.

Mock transport, test-mode Stripe, local PostgreSQL integration or static source validation do not satisfy the live-purchase gate.

## Current external/source blockers

GitHub Actions runner allocation has previously been blocked by the account billing/spending-limit condition observed on node workflows. It must remain `BLOCKED_EXTERNAL` unless a newly allocated runner actually executes the required jobs; it is not a code-test PASS or FAIL.

The root `uv.lock` is stale relative to the current workspace manifest and therefore the canonical frozen install/release gate cannot yet be claimed. The lock must be regenerated by canonical tooling; it must not be hand-edited.

Real AWS Terraform plan/apply, rollback execution, sandbox egress probes, provider budget concurrency proof, alert delivery/human acknowledgement and the Stripe live payment remain runtime evidence requirements.

## Final status

NODE-73 remains **NOT ACCEPTED** until every mandatory item in `reports/nodes/NODE-73/release-acceptance.md` passes with evidence from one exact release candidate.
