# NODE-73 AWS Account Bootstrap Runbook

Status: **required external prerequisite for NODE-71 live Staging**

This runbook exists because the first real Staging `plan-core` run (`32709578553`) failed before Terraform initialization at AWS credential setup. No Terraform plan was created and no AWS mutation occurred. The GitHub `staging` Environment did not contain the required AWS release configuration.

## Safety boundary

The executable CloudShell wrapper is the hosted-validated rerun-safe V2 implementation at exact commit:

`b1e0268df18ca8b2147e05c93635e6953394d07c`

The wrapper itself fetches only the exact bootstrap Terraform source SHA:

`070315c2d3dd697bc87bc3a70acd7a3338175e40`

Script path:

`scripts/aws_release_bootstrap_cloudshell.sh`

The V2 script:

- derives the AWS account id from `sts:GetCallerIdentity`;
- validates the target Region (default `ap-northeast-1`, override with `LUMI_AWS_REGION`);
- installs Terraform **1.14.6** only after official SHA-256 verification for Linux amd64/arm64;
- restores trusted remote/recovery Terraform state **before** deciding GitHub OIDC ownership;
- keeps a Terraform-created GitHub OIDC provider Terraform-managed on rerun instead of converting it into an external input;
- reuses an externally pre-existing GitHub OIDC provider only after validating the canonical issuer and `sts.amazonaws.com` audience;
- fails closed on a possible foreign state-bucket collision, missing trusted state, or divergent local/remote recovery state;
- creates only the account bootstrap root: encrypted/versioned Terraform state, GitHub OIDC trust, and environment-scoped staging/production deploy roles;
- fails if the bootstrap plan contains any delete/replace action;
- refuses apply unless `LUMI_BOOTSTRAP_APPLY=APPLY_AWS_BOOTSTRAP` is explicitly present;
- after apply, writes `$HOME/lumi-aws-bootstrap-recovery.tfstate` with mode 0600 **before** remote state upload;
- uploads state with the exact bootstrap KMS key, verifies the remote object's KMS metadata, downloads the remote state, and requires a byte-for-byte match before deleting the local recovery copy;
- does **not** deploy Staging/Production application resources;
- does **not** write GitHub secrets or variables;
- emits `$HOME/lumi-aws-bootstrap-handoff.json` using `LUMI_AWS_RELEASE_BOOTSTRAP_HANDOFF_V2`, including `bootstrap_state.remote_verified=true`, non-secret release values, and real Region capability candidates.

## Minimal AWS CloudShell execution

Open AWS CloudShell in the intended LUMI AWS account, then run the exact V2 script that passed hosted release validation:

```bash
curl -fsSLo /tmp/lumi-aws-bootstrap.sh \
  https://raw.githubusercontent.com/zhangjaky71-stack/LUMI-AI-DESIGN-OS/b1e0268df18ca8b2147e05c93635e6953394d07c/scripts/aws_release_bootstrap_cloudshell.sh
bash /tmp/lumi-aws-bootstrap.sh
```

The first run is plan-only and intentionally exits before apply after showing a safe plan summary.

If and only if the plan contains no delete/replace actions, run:

```bash
LUMI_BOOTSTRAP_APPLY=APPLY_AWS_BOOTSTRAP bash /tmp/lumi-aws-bootstrap.sh
```

A successful apply writes:

- `$HOME/lumi-aws-bootstrap-handoff.json`
- encrypted/versioned remote bootstrap state at `lumi/bootstrap/terraform.tfstate`

If remote state upload/verification fails after AWS resources were created, the V2 script intentionally leaves `$HOME/lumi-aws-bootstrap-recovery.tfstate` in place. **Do not delete that file manually.** A later V2 rerun will either reconcile it against trusted remote state or restore it when remote state is absent; divergent states fail closed rather than being chosen automatically.

## Stage 1 — values required before `plan-core`

The V2 bootstrap handoff automatically provides/derives:

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

The canonical Staging workflow runs `scripts/validate_staging_environment_preflight.py` **before** AWS OIDC. For `plan-core`/`apply-core` it validates only the AWS/bootstrap/core values above and writes `environment-preflight.json` containing key names/status only; it never records secret values.

### No longer required as GitHub secrets

Do **not** create these historical GitHub Environment secrets:

- `REDIS_AUTH_TOKEN`
- `RABBITMQ_USERNAME`
- `RABBITMQ_PASSWORD`

Staging core generates Redis and RabbitMQ credentials inside Terraform, writes the connection URLs to Secrets Manager with write-only secret version attributes, and rejects those old manual TF_VAR inputs. It also generates the internal authentication/control secret set with Terraform ephemeral random passwords:

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

Before the migration/app stages can be accepted, the dedicated database-role bootstrap tracked in issue `#144` must create least-privilege migration/application database identities from the real RDS master trust boundary and seed `database/migration` / `database/app` without exposing the master password to GitHub or ordinary Terraform state.

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
- Rerun-safe bootstrap V2 source commit: `b1e0268df18ca8b2147e05c93635e6953394d07c`.
- Production IaC Contract run `33038293845`: **SUCCESS** — bootstrap semantic contract, Python/Shell syntax, Terraform fmt and all eight release roots init/validate passed.
- Staging Release Ops Contract run `33038293943`: **SUCCESS**.
- Runtime Image Closure Contract run `33038293890`: **SUCCESS**.
- standalone CodeQL run `33038293867`: **SUCCESS**.
- Security Release Gate run `33038293846`: all substantive code/security jobs **SUCCESS**; only Dependency Review fails because repository Dependency Graph is not enabled, so the aggregate release gate remains fail-closed red as designed.

## Release sequence after AWS bootstrap

1. populate only the protected `staging` Environment values required for `plan-core` from the V2 handoff and Region-validated pins;
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
