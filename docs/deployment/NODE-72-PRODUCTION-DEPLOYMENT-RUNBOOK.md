# NODE-72 — Production Deployment Runbook

> Status: **SOURCE RUNBOOK / NOT YET EXECUTED IN PRODUCTION**

## 1. Purpose

This runbook is the operator sequence for taking the exact release candidate accepted by NODE-71 into LUMI Production. It is fail-closed: a missing acceptance decision, mutable image, empty Secret, failed snapshot, failed migration, incomplete ECS deployment, or smoke mismatch stops the rollout.

## 2. Required evidence before any production mutation

Prepare these committed evidence files:

```text
reports/staging-acceptance/<rc>/decision.json
reports/production-deployments/<deployment-id>/manifest.json
```

The NODE-71 decision must contain `passed=true`. The production manifest must match the same exact:

```text
RC Git SHA
RC version
migration head
NODE-71 decision_id
six immutable image digests
```

`python3 scripts/production-deployment-gate.py` performs the binding check.

## 3. One-time AWS prerequisites

These are account/authorization tasks and cannot be truthfully marked complete by source code alone:

1. Dedicated Staging and Production AWS accounts or equivalent isolation.
2. GitHub Actions OIDC provider for `token.actions.githubusercontent.com`.
3. Terraform state bootstrap applied in the target account.
4. GitHub Environments `staging` and `production` with deployment protection/approvers.
5. Production Environment variables/secrets populated for AWS account/region/role/state/engine pins/domain.
6. Route53 hosted zone and ACM certificate available in the selected region.
7. Provider/billing/email/support dependencies in the production manifest are `READY` or explicitly `DISABLED_BY_RELEASE_SCOPE`.

## 4. Core provisioning

Use `Deploy Production` with `plan-core` first. Review the Terraform plan for:

- three AZ topology;
- public/private/data subnet separation;
- no public RDS/Redis/MQ;
- RDS Multi-AZ/backups/deletion protection;
- Redis TLS/at-rest encryption;
- RabbitMQ CLUSTER_MULTI_AZ;
- private S3/KMS/versioning/lifecycle;
- expected Secret containers only.

Then run `apply-core` with:

```text
DEPLOY_PRODUCTION:<deployment-id>
```

Do not proceed if core outputs differ from the reviewed architecture.

## 5. Fill Secret Versions

Terraform deliberately leaves Secret values empty. Populate the eight required Secrets through the approved secure operations path:

```text
database/app
database/migration
redis/url
rabbitmq/url
providers/model
providers/media
billing/webhook
auth/signing
```

Do not paste values into tfvars or commit them.

The production workflow calls `scripts/check-aws-secret-versions.sh`; every Secret must have an `AWSCURRENT` version before migration.

## 6. Release plan

Run `plan-release` after NODE-71 acceptance and Secret preparation. It plans both:

```text
production/migration
production/app
```

Review at minimum:

- migration image equals accepted API image digest;
- application image digests equal manifest;
- API port is 8000;
- only API is publicly routed;
- public API uses 5% ECS canary with 10-minute bake and alarm rollback;
- internal services use rolling circuit breaker;
- task roles have only declared bucket/secret permissions;
- no public task IP;
- DNS/WAF target expected ALB.

## 7. Deploy release

Trigger `deploy-release` with exact acknowledgement:

```text
DEPLOY_PRODUCTION:<deployment-id>
```

The workflow executes in this order:

```text
Production Gate
-> AWS OIDC / exact account verification
-> Secret AWSCURRENT validation
-> RDS availability / backup retention check
-> manual pre-deployment RDS snapshot + wait
-> migration Terraform plan/apply
-> Fargate Alembic task
-> advisory migration lock
-> require migration exit code 0
-> app Terraform plan/apply
-> ECS native API canary + internal rolling deploy
-> Terraform waits for steady state
-> capture ECS service/deployment evidence
-> HTTPS health/ready/version/security-header smoke
-> archive evidence artifact
```

If any command exits non-zero, do not manually skip to a later step.

## 8. Database migration rules

- Migrations use `MIGRATION_DATABASE_URL`, not the application DB credential.
- Alembic takes a PostgreSQL advisory lock; concurrent migration attempts must fail rather than overlap.
- Pre-deployment snapshot must be `available` before migration begins.
- Release manifest must explicitly assert database backward compatibility with the previous deployment.
- Prefer expand-compatible migrations before switching application traffic. Destructive contract migrations belong in a later controlled release after old code is retired.

## 9. Public API canary

The API uses AWS ECS-native canary deployment:

```text
5% green traffic
-> 10-minute observation/bake
-> 100% if healthy
```

Rollback alarms monitor the alternate/green target group for repeated target 5xx and unhealthy hosts. The Terraform apply is configured to wait for ECS steady state before the workflow continues.

Do not call a rollout successful until `ecs-deployment-state.json` and `production-smoke.json` both pass.

## 10. Internal services

Agent Runtime, Model Gateway, Tool Gateway, Media Worker and Sandbox Runtime use rolling ECS deployment plus circuit-breaker rollback because they are not directly routed through public user traffic in this topology.

Their correctness still requires queue/agent/provider Staging acceptance; infrastructure steady state alone is not product correctness.

## 11. Rollback

The deployment manifest records:

```text
previous_deployment_id
previous_manifest_ref
database_backward_compatible=true
```

For API canary failure, ECS should automatically roll back before full promotion. For a post-promotion application rollback:

1. Stop new risky feature flags/provider routes if applicable.
2. Re-run the production gate against the approved previous immutable image manifest.
3. Confirm DB remains backward compatible.
4. Apply previous app image digests; do **not** blindly restore DB snapshot for an application-only rollback.
5. Verify ECS steady state and read-only smoke.
6. If DB corruption/schema recovery is actually required, use NODE-68 recovery procedures and treat it as an incident, not a routine app rollback.

A real rollback drill in Staging/Production-equivalent infrastructure is required before NODE-72 can be called complete.

## 12. First-day controls

Infrastructure-enforced controls include:

- WAF per-IP rate limit;
- ECS min/max capacity;
- conservative desired counts;
- Model Gateway request-local budget checks and Billing credit/usage controls elsewhere in the system.

The production manifest also records org concurrency/video/provider-spend/invite limits. However, a platform-wide daily provider-dollar hard stop is not yet proven as a durable runtime control. Do not treat the manifest value alone as enforcement.

## 13. Known deployment blockers

NODE-72 source currently does not prove:

- a real AWS account has been provisioned;
- NODE-71 has a passed RC decision;
- the six intended production runtime images exist and are reproducibly built/promoted;
- transport/server entrypoints exist for every intended network runtime;
- required Secret values and commercial provider credentials exist;
- actual canary/alarm rollback has run;
- production DNS/TLS/WAF are live;
- platform-wide daily provider spend hard-stop exists;
- sandbox egress is isolated at production network level;
- GitHub hosted CI can execute despite the account Billing/spending-limit blocker seen on preceding nodes.

Any of these can remain as source work, but Production must not be declared live until the relevant P0 evidence is PASS.
