# LUMI Production Infrastructure (NODE-72)

> Status: **SOURCE IMPLEMENTED / CLOUD EXECUTION REQUIRED**

This directory defines the production-like AWS reference deployment for LUMI AI Design OS. It is intentionally split into reusable modules and three independent environment states so database migration cannot race the first application deployment.

## Reference topology

```text
Route53
  -> AWS WAF
  -> public ALB (TLS)
      -> ECS/Fargate API (private subnet, no public IP)

Private ECS/Fargate service boundary
  api
  agent-runtime
  model-gateway
  tool-gateway
  worker-media
  sandbox-runtime
      -> Cloud Map private discovery

Data subnets (no Internet default route)
  RDS PostgreSQL / Multi-AZ / PITR
  ElastiCache Redis / Multi-AZ / TLS
  Amazon MQ RabbitMQ / CLUSTER_MULTI_AZ / AMQPS

Private S3
  assets
  exports
  sandbox

KMS + Secrets Manager
```

The six ECS names are the intended production deployment boundaries. A repository package existing under `services/` does not by itself prove that an independently deployable HTTP/worker runtime exists. Runtime transport/image readiness must be proven in Staging before its image digest is admitted to NODE-71/NODE-72 evidence.

## Three-stage state model

Each environment has three separate Terraform states:

```text
core
  -> network, KMS/S3, RDS/Redis/MQ, Secret containers

migration
  -> isolated one-shot ECS/Alembic task definition

app
  -> ECS services, service discovery, ALB, native ECS canary, WAF, DNS
```

The safe ordering is:

```text
core apply
-> inject/rotate Secret Versions outside Terraform
-> verify AWSCURRENT on every required Secret
-> create RDS pre-deploy snapshot
-> migration stack apply
-> run one-shot Alembic task and require exit 0
-> app plan/apply
-> wait for ECS steady state
-> read-only production smoke
```

Do not merge the migration runner into the app state and do not use `terraform -target` as a deployment orchestrator.

## Environments

Staging and Production call the same modules:

```text
infra/iac/environments/staging/{core,migration,app}
infra/iac/environments/production/{core,migration,app}
```

They differ in account/network/domain/capacity/protection settings, not topology class. Both require three distinct availability zones.

## Terraform toolchain

The NODE-72 contract pins:

```text
Terraform CLI: >= 1.14.6, < 1.15.0
AWS Provider:  = 6.55.0
```

The pinned AWS Provider is required because the ECS-native CANARY deployment schema is part of the release contract. Do not casually widen the provider constraint; upgrade through a reviewed NODE-72 contract change and Staging plan.

## Public API deployment strategy

The one publicly routed service uses ECS-native canary deployment:

```text
blue target group
+ green alternate target group
+ production listener rule
+ ECS infrastructure load-balancer role
+ 5% canary
+ 10 minute bake
+ green 5xx / unhealthy alarms
+ automatic rollback
+ wait_for_steady_state
```

Internal/headless services use ECS rolling deployment plus deployment circuit-breaker rollback.

## Network rules

- Only ALB/NAT resources live in public subnets.
- ECS tasks use private subnets and `assign_public_ip = false`.
- Data services use data subnets with no Internet default route.
- The public ALB reaches the API only on the real API port `8000`.
- RDS/Redis/RabbitMQ accept traffic only from the application security group.
- Sandbox shares the application SG in this baseline; dedicated egress isolation remains a production security validation item and must not be silently treated as complete.

## Secret values

Terraform creates Secret Manager containers only. It deliberately does **not** create `aws_secretsmanager_secret_version` resources for application credentials.

Required values:

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

Secret values are injected by the protected environment/operations process after core provisioning. `scripts/check-aws-secret-versions.sh` verifies every required secret has `AWSCURRENT` before production migration starts.

## State bootstrap and GitHub OIDC

`infra/iac/bootstrap/` creates:

- KMS-encrypted, private, versioned Terraform state bucket;
- GitHub Actions deploy roles for `environment:staging` and `environment:production`.

An account-level IAM OIDC provider for `token.actions.githubusercontent.com` is an explicit prerequisite. The bootstrap trust policy pins the repository and GitHub Environment subject. The bootstrap/provisioner role has broad platform-provisioning permissions; it is **not** described as runtime least privilege. ECS runtime task roles remain per-service and much narrower.

## Production gate

`.github/workflows/deploy-production.yml` will not deploy from an arbitrary SHA. It requires a completed production manifest and the exact NODE-71 decision that accepted the same:

```text
git_sha
version
migration_head
staging decision_id
image digests
```

The deployment manifest also freezes rollout policy, rollback target, dependencies, approvals, and first-day limits.

## Source validation

```bash
python3 scripts/validate_production_deployment_contract.py
python3 scripts/validate_production_iac_contract.py
terraform fmt -check -recursive infra/iac
```

GitHub Actions additionally runs `terraform init -backend=false` and `terraform validate` for every root when runners are available.

## STOP SHIP items

This source tree is not proof of a production deployment. Production remains blocked until at least:

- NODE-71 returns `passed=true` for the exact immutable RC;
- AWS account/OIDC/state/DNS/TLS resources are actually provisioned;
- required Secret Versions exist;
- every intended runtime has a real production entrypoint and reproducible image build/promotion pipeline;
- the exact images are exercised in Staging and pinned by digest;
- migrations, canary, alarm rollback, ECS steady state, and rollback are exercised with evidence;
- the platform-wide daily provider-spend hard stop is durably enforced (request-level budgets/credits alone are not this control);
- sandbox production network isolation is reviewed against NODE-66 threat model;
- hosted CI can execute rather than being blocked before runner start.
