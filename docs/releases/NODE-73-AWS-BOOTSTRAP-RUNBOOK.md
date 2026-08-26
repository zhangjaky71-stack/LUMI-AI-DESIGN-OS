# NODE-73 AWS Account Bootstrap Runbook

Status: **required external prerequisite for NODE-71 live Staging**

This runbook exists because the first real Staging `plan-core` run (`32709578553`) failed before Terraform initialization at AWS credential setup. No Terraform plan was created and no AWS mutation occurred. The GitHub `staging` Environment did not contain the required AWS release configuration.

## Safety boundary

The bootstrap script is pinned internally to the hosted-validated bootstrap source SHA:

`070315c2d3dd697bc87bc3a70acd7a3338175e40`

Script path:

`scripts/aws_release_bootstrap_cloudshell.sh`

The script:

- derives the AWS account id from `sts:GetCallerIdentity`;
- validates the target Region (default `ap-northeast-1`, override with `LUMI_AWS_REGION`);
- installs Terraform **1.14.6** only after SHA-256 verification;
- reuses an existing GitHub Actions OIDC provider or lets Terraform create it;
- creates only the account bootstrap root: encrypted/versioned Terraform state, GitHub OIDC trust, and environment-scoped staging/production deploy roles;
- fails if the bootstrap plan contains any delete/replace action;
- refuses apply unless `LUMI_BOOTSTRAP_APPLY=APPLY_AWS_BOOTSTRAP` is explicitly present;
- does **not** deploy Staging/Production application resources;
- does **not** write GitHub secrets or variables;
- emits `$HOME/lumi-aws-bootstrap-handoff.json` containing the non-secret values needed by later release configuration and real Region capability candidates.

## Minimal AWS CloudShell execution

Open AWS CloudShell in the intended LUMI AWS account, then run the pinned script from the validated release history:

```bash
curl -fsSLo /tmp/lumi-aws-bootstrap.sh \
  https://raw.githubusercontent.com/zhangjaky71-stack/LUMI-AI-DESIGN-OS/20da7ab01b515667585a8d91dc6cec46fdbeef5b/scripts/aws_release_bootstrap_cloudshell.sh
bash /tmp/lumi-aws-bootstrap.sh
```

The first run is plan-only and intentionally exits before apply after showing a safe plan summary.

If and only if the plan contains no delete/replace actions, run:

```bash
LUMI_BOOTSTRAP_APPLY=APPLY_AWS_BOOTSTRAP bash /tmp/lumi-aws-bootstrap.sh
```

The successful run writes:

`$HOME/lumi-aws-bootstrap-handoff.json`

## Stage 1 — values required before `plan-core`

The bootstrap handoff automatically provides/derives:

- `AWS_ACCOUNT_ID`
- `AWS_REGION`
- `AWS_AVAILABILITY_ZONES_JSON`
- `AWS_DEPLOY_ROLE_ARN`
- `TERRAFORM_STATE_BUCKET`
- GitHub OIDC provider ARN
- Terraform-state KMS ARN
- Region capability candidates for PostgreSQL, Redis, and RabbitMQ

The protected GitHub `staging` Environment must use the handoff values plus Region-validated service pins:

- `POSTGRES_ENGINE_VERSION`
- `REDIS_ENGINE_VERSION`
- `RABBITMQ_ENGINE_VERSION`
- `RABBITMQ_INSTANCE_TYPE`

The canonical Staging workflow now runs `scripts/validate_staging_environment_preflight.py` **before** AWS OIDC. For `plan-core`/`apply-core` it validates only the AWS/bootstrap/core values above and writes `environment-preflight.json` containing key names/status only; it never records secret values.

### No longer required as GitHub secrets

Do **not** create these historical GitHub Environment secrets:

- `REDIS_AUTH_TOKEN`
- `RABBITMQ_USERNAME`
- `RABBITMQ_PASSWORD`

Staging core now generates Redis and RabbitMQ credentials inside Terraform, writes the connection URLs to Secrets Manager with write-only secret version attributes, and rejects those old manual TF_VAR inputs. It also generates the internal authentication/control secret set with Terraform ephemeral random passwords:

- `auth/signing`
- `internal/model-gateway`
- `internal/tool-gateway`
- `internal/sandbox-runtime`
- `internal/side-effect-control`
- `internal/tool-audit`
- `internal/tool-approval`
- `internal/tool-data`
- `internal/agent-control`

These generated values must not be copied back into GitHub.

## Stage 2 — after `apply-core`, before migration

Core creates the Secrets Manager containers for:

- `database/app`
- `database/migration`
- `providers/model`
- `providers/media`
- `providers/search`
- `billing/webhook`

It also creates RDS PostgreSQL with `manage_master_user_password = true`, so the master credential remains AWS-managed. The repository must **not** reuse that master credential as the long-lived application database credential.

Before the migration/app stages can be accepted, a dedicated database-role bootstrap must create least-privilege migration/application database identities from the real RDS master trust boundary and seed `database/migration` / `database/app` without exposing the master password to GitHub or Terraform state. Until that live step is implemented and proven, do not invent or manually paste database URLs.

Migration/app operations additionally require the exact promoted six-image ECR digest map derived from frozen runtime-image build run `32704633686`; no rebuild is allowed.

## Stage 3 — before App deployment / live provider evidence

App deployment additionally requires real DNS/certificate/media configuration:

- `ACM_CERTIFICATE_ARN`
- `API_DOMAIN_NAME`
- `ROUTE53_HOSTED_ZONE_ID`
- `VIDEO_MODEL_PROFILE`

The following Secrets Manager values are real external integrations and are intentionally **not synthesized** by Terraform:

- `providers/model`
- `providers/media`
- `providers/search`
- `billing/webhook`

Only approved live provider credentials/configuration may populate those secrets. Synthetic placeholders cannot be used as NODE-71 live-provider acceptance evidence.

## Evidence already established

- Six-runtime RC build/freeze: workflow run `32704633686`, exact RC SHA `3c6a95356a013c2bdf505bde14a7fcfcc33c32a9`.
- Failed real Staging attempt: workflow run `32709578553`, issue `#138`, state `FAILED_PRECONDITION`, no AWS mutation.
- AWS bootstrap blocker/handoff: issue `#143`.
- Latest preflight-enabled Staging Release Ops contract: run `32926106063`, full success.
- Prior current-IaC baseline on the ephemeral-secret head: Production IaC run `32832799734`, Runtime Image Closure run `32832799819`, and CodeQL run `32832799911` all succeeded.
- Security Release Gate run `32832799774` passed every substantive code/security job except the independent repository Dependency Graph / Dependency Review platform blocker.

## Release sequence after AWS bootstrap

1. populate only the protected `staging` Environment values required for `plan-core` from the bootstrap handoff and Region-validated pins;
2. rerun canonical Staging `plan-core`;
3. inspect the emitted Terraform plan and require no destructive/replace data-layer actions;
4. only then run `apply-core` with explicit mutation acknowledgement;
5. promote the exact frozen six-runtime GHCR image set into Terraform-managed Staging ECR without rebuild and require digest preservation;
6. establish and prove least-privilege `database/migration` and `database/app` identities from the real RDS trust boundary;
7. plan/apply migration and run the one-shot migration;
8. configure approved provider/DNS/media values, then plan/apply App with the exact promoted six-image set;
9. collect real database/media/Tool Gateway/private-Model-Gateway evidence;
10. freeze and dispatch NODE-71 Staging Acceptance against runtime-image build run `32704633686` and RC SHA `3c6a95356a013c2bdf505bde14a7fcfcc33c32a9`.

NODE-71 and NODE-73 remain blocked until this real Staging chain completes and the sealed NODE-71 decision is `passed=true`.
