# NODE-72 — Production Deployment & Infrastructure — Release Evidence

> Status: **SOURCE IMPLEMENTED / CLOUD VALIDATION PENDING / GO-LIVE BLOCKED**  
> Evidence date: 2026-08-15  
> Branch: `node-72-production-deployment-release`

## 1. Current decision

NODE-72 has a production deployment **control plane and IaC source baseline**, but it is **not production-ready and has not deployed LUMI to Production**.

A Terraform source tree, deployment workflow, or successful source-contract fixture is not proof that Production exists. Production PASS requires the exact NODE-71 accepted RC to be provisioned, migrated, canaried, observed, smoke-tested and rollback-tested in the target cloud environment.

Current release decision:

```text
SOURCE IMPLEMENTED
CLOUD VALIDATION PENDING
PRODUCTION NOT PROVISIONED BY THIS EVIDENCE
GO-LIVE BLOCKED
```

## 2. Source controls implemented

### Release identity and fail-closed deployment gate

- exact NODE-71 `decision.json` is required;
- NODE-71 must report `passed=true`;
- deployment manifest must bind the same Git SHA, RC version and migration head;
- deployment manifest pins exactly six runtime image identities by immutable `@sha256` digest;
- mutable image tags are rejected;
- rollback target and DB backward compatibility must be explicitly declared;
- external dependency and engineering/security/release approvals must be ready;
- production evidence paths are constrained to the repository evidence archives.

Primary source:

```text
production/deployment/manifest-template.json
scripts/production-deployment-gate.py
scripts/validate_production_deployment_contract.py
```

### AWS/Terraform reference infrastructure

Implemented modules:

```text
network
storage
data
secrets
compute
edge
platform-core
platform-app
migration-runner
```

The topology encodes:

- three-AZ public/private/data subnet classes;
- public ALB only; ECS tasks remain private with no public IP;
- RDS PostgreSQL private, encrypted, Multi-AZ and backup/PITR configured;
- Redis Multi-AZ/failover with transit and at-rest encryption;
- Amazon MQ RabbitMQ `CLUSTER_MULTI_AZ`, private subnets and AMQPS boundary;
- private KMS-encrypted/versioned S3 buckets for assets/exports/sandbox;
- Secrets Manager metadata containers without storing secret values in Terraform;
- per-service ECS task/execution roles;
- Cloud Map private service discovery;
- WAF managed rules and rate limiting;
- Route53/HTTPS ALB edge;
- custom backlog/concurrency autoscaling metrics instead of CPU-only scaling.

### Environment parity and deployment ordering

Staging and Production use the same Terraform modules and the same three-state lifecycle:

```text
core
-> secret population/readiness
-> migration
-> app
```

The migration stack is intentionally separate from the application stack so first deployment cannot start application services before schema migration completes.

### Database deployment safety

- `MIGRATION_DATABASE_URL` is separate from the application credential;
- Alembic takes a PostgreSQL advisory migration lock;
- production release creates and waits for a pre-deploy RDS snapshot;
- migration is a one-shot Fargate task, not a continuously reconciled ECS service;
- migration task exit code must be zero before application rollout.

### Public API deployment safety

- real API port is pinned to 8000, matching the API CLI;
- public API uses two ALB target groups;
- ECS-native `CANARY` strategy sends an initial 5% to green;
- default bake/observation interval is 10 minutes;
- green-target 5xx and unhealthy-host CloudWatch alarms are configured for rollback;
- Terraform waits for ECS steady state;
- deployment state is independently captured and verifies running/desired/pending/PRIMARY rollout state;
- final Production smoke is HTTPS GET-only and checks live/ready/version/security headers.

Internal/headless services use rolling ECS deployments with circuit-breaker rollback.

### Supply-chain/tooling source constraints

- Terraform CLI contract: `>= 1.14.6, < 1.15.0`;
- AWS provider contract: `= 6.55.0`;
- production images must be immutable digests;
- GitHub Actions uses OIDC instead of committed AWS access keys;
- production OIDC trust is scoped to the repository and protected `production` Environment subject;
- Terraform creates Secret containers only; actual Secret Versions are provisioned by the protected operations path.

## 3. Source validation staged

`Production IaC Contract` contains:

- dependency-free production deployment negative drills;
- dependency-free infrastructure invariants;
- Python syntax checks;
- shell syntax checks for secret/snapshot/migration/ECS-state scripts;
- production manifest JSON validation;
- recursive `terraform fmt -check`;
- backend-disabled `terraform init` + `terraform validate` for bootstrap, Staging core/migration/app and Production core/migration/app;
- final contract job requiring both source and Terraform validation to succeed.

This workflow still needs to **actually execute on a GitHub runner** before it can be counted as validation evidence.

## 4. Runtime evidence required before PASS

All boxes remain intentionally unchecked until real evidence exists.

### Repository / CI

- [ ] NODE-72 `Production IaC Contract` actually receives a runner and executes green.
- [ ] Terraform format and validation jobs execute green with the pinned toolchain.
- [ ] The inherited root `uv.lock` freshness / canonical supply-chain blocker from NODE-66 is resolved.
- [ ] Canonical security and repository release gates execute green.

### NODE-71 / exact release candidate

- [ ] NODE-71 has a real Production-like Staging environment.
- [ ] NODE-71 returns an evidenced `passed=true` decision for an exact RC.
- [ ] NODE-70 real AI release evidence is attached to that RC.
- [ ] NODE-69 launch-profile/capacity evidence exists for that RC.

### Cloud provisioning

- [ ] Dedicated/approved Staging and Production AWS isolation is available.
- [ ] GitHub OIDC provider is configured in the target AWS account(s).
- [ ] Encrypted/versioned Terraform state backend is applied.
- [ ] Production core `terraform plan` is reviewed.
- [ ] Production core `terraform apply` succeeds.
- [ ] Network reachability negative tests prove DB/Redis/MQ are not public.
- [ ] Runtime IAM least-privilege checks are executed against real roles.
- [ ] Route53/ACM/TLS/WAF are live on the production domain.

### Secrets / providers / support

- [ ] All eight required Secret Versions exist with `AWSCURRENT`.
- [ ] Secret rotation procedure is tested.
- [ ] Model/media provider credentials and quotas are production-ready.
- [ ] Billing webhook production endpoint/secret is validated.
- [ ] Email domain is production-ready or the feature is explicitly disabled.
- [ ] Support/on-call ownership is active.

### Runtime images and transports

- [ ] `api` production image is reproducibly built, scanned and promoted from Staging by digest.
- [ ] `agent-runtime` has a real production runtime entrypoint/image and is exercised in Staging.
- [ ] `model-gateway` has a real production transport/server entrypoint/image and is exercised in Staging.
- [ ] `tool-gateway` has a real production transport/server entrypoint/image and is exercised in Staging.
- [ ] `worker-media` production worker image is exercised in Staging.
- [ ] `sandbox-runtime` has a real production control-plane/runtime entrypoint/image and is exercised in Staging.
- [ ] SBOM/vulnerability scan evidence exists for the exact promoted images.
- [ ] Production reuses the exact Staging-accepted image digests; it does not rebuild them.

### Database / recovery

- [ ] Pre-deploy RDS snapshot completes and is archived as evidence.
- [ ] One-shot Alembic migration completes with exit code 0.
- [ ] Backward-compatible rollback is proven for the release migration set.
- [ ] NODE-68 Production-like restore/PITR evidence satisfies the release policy.
- [ ] Backup alarms and restore procedures are tested in the target topology.

### Deployment / canary / rollback

- [ ] Production app plan is reviewed after migration succeeds.
- [ ] API 5% native canary actually executes against the exact RC.
- [ ] Canary 5xx/unhealthy alarm rollback is deliberately exercised in a safe environment.
- [ ] Internal services reach ECS steady state.
- [ ] `ecs-deployment-state.json` passes for all intended services.
- [ ] `production-smoke.json` passes against the production domain/version.
- [ ] Post-promotion rollback to the previous immutable deployment is exercised.
- [ ] Service restart and autoscaling drills are executed.

### Security / cost controls

- [ ] Production sandbox has reviewed network/egress isolation consistent with NODE-66 threat model.
- [ ] Production WAF/rate-limit behavior is exercised.
- [ ] First-day org/run/video/invite limits are proven at the runtime enforcement point.
- [ ] Platform-wide daily provider-dollar hard stop is durably enforced; a manifest value alone is not sufficient.
- [ ] Provider outage/reconciliation tests show no duplicate paid effect.

## 5. Known STOP SHIP items at source-baseline close

1. NODE-71 does not yet have a real `passed=true` Staging RC decision.
2. NODE-72 cloud resources have not been provisioned by this evidence.
3. Real Secret Versions and commercial credentials have not been proven.
4. The six intended production deployment boundaries do not all yet have independently proven production transport/entrypoint + reproducible image promotion pipelines.
5. Real canary, alarm rollback and post-promotion rollback evidence do not exist yet.
6. Sandbox production egress isolation remains to be hardened/reviewed.
7. A platform-wide daily provider-dollar hard stop is not yet proven as a durable runtime control.
8. NODE-68/69/70/71 Production-like runtime evidence remains incomplete.
9. GitHub Actions on preceding readiness nodes has been blocked before runner start by the account Billing/spending-limit condition; NODE-72 must collect its **own** runner evidence rather than infer PASS or failure from those nodes.

## 6. Evidence locations

```text
infra/iac/README.md
infra/iac/bootstrap/
infra/iac/modules/
infra/iac/environments/staging/
infra/iac/environments/production/
production/deployment/manifest-template.json
.github/workflows/production-iac-contract.yml
.github/workflows/deploy-staging-infrastructure.yml
.github/workflows/deploy-production.yml
scripts/production-deployment-gate.py
scripts/validate_production_deployment_contract.py
scripts/validate_production_iac_contract.py
scripts/check-aws-secret-versions.sh
scripts/create-predeploy-rds-snapshot.sh
scripts/ecs-run-one-shot-task.sh
scripts/capture-ecs-deployment-state.sh
scripts/production-read-only-smoke.py
docs/deployment/NODE-72-PRODUCTION-DEPLOYMENT-RUNBOOK.md
reports/production-deployments/README.md
```

## 7. Completion rule

NODE-72 may move to COMPLETE only when the Production Definition of Done is evidenced:

```text
production infrastructure provisioned
+ exact NODE-71 accepted RC deployed through controlled CI/CD
+ canary/alarms successful
+ smoke/SLO green
+ rollback path exercised
+ required security/recovery/cost controls proven
```

Until then, the correct status remains:

**SOURCE IMPLEMENTED / CLOUD VALIDATION PENDING / GO-LIVE BLOCKED**.
