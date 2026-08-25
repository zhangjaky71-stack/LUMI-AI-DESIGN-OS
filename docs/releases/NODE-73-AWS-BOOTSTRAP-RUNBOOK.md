# NODE-73 AWS Account Bootstrap Runbook

Status: **required external prerequisite for NODE-71 live Staging**

This runbook exists because the first real Staging `plan-core` run (`32709578553`) failed before Terraform initialization at AWS credential setup. No Terraform plan was created and no AWS mutation occurred. The GitHub `staging` Environment did not contain the required AWS release configuration.

## Safety boundary

The bootstrap script is pinned to the hosted-validated bootstrap source SHA:

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

Open AWS CloudShell in the intended LUMI AWS account, then run:

```bash
git clone https://github.com/zhangjaky71-stack/LUMI-AI-DESIGN-OS.git
cd LUMI-AI-DESIGN-OS
git checkout 20da7ab01b515667585a8d91dc6cec46fdbeef5b
bash scripts/aws_release_bootstrap_cloudshell.sh
```

The first run is plan-only and intentionally exits before apply after showing a safe plan summary.

If and only if the plan contains no delete/replace actions, run:

```bash
LUMI_BOOTSTRAP_APPLY=APPLY_AWS_BOOTSTRAP bash scripts/aws_release_bootstrap_cloudshell.sh
```

The successful run writes:

`$HOME/lumi-aws-bootstrap-handoff.json`

## Values still required after bootstrap

The bootstrap handoff automatically provides/derives:

- `AWS_ACCOUNT_ID`
- `AWS_REGION`
- `AWS_AVAILABILITY_ZONES_JSON`
- `AWS_DEPLOY_ROLE_ARN`
- `TERRAFORM_STATE_BUCKET`
- GitHub OIDC provider ARN
- Terraform-state KMS ARN
- Region capability candidates for PostgreSQL, Redis, and RabbitMQ

Before another live Staging plan can succeed, the protected GitHub `staging` Environment must also contain validated service pins and generated secrets required by `infra/iac/environments/staging/core`:

- `POSTGRES_ENGINE_VERSION`
- `REDIS_ENGINE_VERSION`
- `RABBITMQ_ENGINE_VERSION`
- `RABBITMQ_INSTANCE_TYPE`
- `REDIS_AUTH_TOKEN` (secret)
- `RABBITMQ_USERNAME` (secret)
- `RABBITMQ_PASSWORD` (secret)

App deployment additionally requires the real DNS/certificate/media values:

- `ACM_CERTIFICATE_ARN`
- `API_DOMAIN_NAME`
- `ROUTE53_HOSTED_ZONE_ID`
- `VIDEO_MODEL_PROFILE`

Do not guess these values and do not commit credentials to the repository.

## Evidence already established

- Six-runtime RC build/freeze: workflow run `32704633686`, exact RC SHA `3c6a95356a013c2bdf505bde14a7fcfcc33c32a9`.
- Failed real Staging preflight: workflow run `32709578553`, issue `#138`, state `FAILED_PRECONDITION`, no AWS mutation.
- Production IaC hosted contract on the CloudShell-script head: run `32715176700`, full success.
- Staging Release Ops hosted contract on the same head: run `32715176775`, full success.
- Runtime Image Closure on the same head: run `32715177078`, success.
- Security code checks remain green except the independent repository Dependency Graph / Dependency Review platform blocker.

NODE-71 and NODE-73 remain blocked until a real Staging plan/apply and sealed live evidence chain complete successfully.
