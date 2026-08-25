# NODE-73 AWS / Staging Bootstrap Blocker Evidence

Status: **FAILED_PRECONDITION / EXTERNAL AWS ACCOUNT BOOTSTRAP REQUIRED**

This document records the first real NODE-71 Staging infrastructure attempt and the exact boundary that prevented Terraform planning. It is failure/precondition evidence only. It is **not** NODE-71 Staging PASS evidence and must never be used to change the NODE-73 Final Acceptance verdict.

## Frozen runtime release candidate

The live runtime release candidate remains immutable and unchanged:

- release Git SHA: `3c6a95356a013c2bdf505bde14a7fcfcc33c32a9`
- RC branch anchor: `node-73-rc-3c6a9535`
- canonical runtime-image build/freeze run: `32704633686`
- runtime-image-set artifact id: `9511981806`
- runtime-image-set artifact digest: `sha256:48cae885db03882ce40d08424cd5c5cb00c20af4dca62842ff24638f4ac42ed4`
- attestation status: `PASS`
- runtime count: `6`

The later release-orchestration commits do not alter this frozen RC identity.

## First real Staging `plan-core` attempt

Canonical workflow:

- workflow: `.github/workflows/deploy-staging-infrastructure.yml`
- request id: `node-73-staging-plan-core-20260824-01`
- request source commit: `d075839c922b829972067abd9aced9506b5b724b`
- workflow-dispatch run id: `32709578553`
- audit issue: `#138`
- requested operation: `plan-core`

Result: **FAILURE — FAILED_PRECONDITION**.

The workflow failed at the pinned `aws-actions/configure-aws-credentials` step before Terraform backend initialization. The exact first error was:

```text
Input required and not supplied: aws-region
```

The hosted job environment confirmed that the Staging GitHub Environment/repository AWS release configuration had not been provisioned.

## Missing environment inputs observed at runtime

The following values were empty in the real run:

- `AWS_REGION`
- `AWS_DEPLOY_ROLE_ARN`
- `TERRAFORM_STATE_BUCKET`
- `AWS_ACCOUNT_ID`
- `AWS_AVAILABILITY_ZONES_JSON`
- `POSTGRES_ENGINE_VERSION`
- `REDIS_ENGINE_VERSION`
- `RABBITMQ_ENGINE_VERSION`
- `RABBITMQ_INSTANCE_TYPE`
- `REDIS_AUTH_TOKEN`
- `RABBITMQ_USERNAME`
- `RABBITMQ_PASSWORD`

App-only configuration such as `ACM_CERTIFICATE_ARN`, `API_DOMAIN_NAME`, `ROUTE53_HOSTED_ZONE_ID`, and `VIDEO_MODEL_PROFILE` was also absent and remains required before App deployment.

## Safety result of the failed run

The failed run made no infrastructure change:

- AWS OIDC credential session: **NOT ESTABLISHED**
- Terraform backend init: **NOT STARTED**
- Terraform plan: **NOT CREATED**
- Terraform apply: **NOT STARTED**
- runtime image promotion: **NOT STARTED**
- AWS mutation: **NONE**
- NODE-71 Staging acceptance decision: **NOT RUN**

## Repository-side remediation already completed

The repository now contains a self-contained AWS bootstrap path and validated Staging release orchestration:

1. `infra/iac/bootstrap/`
   - can create the account-level GitHub Actions OIDC provider when absent;
   - can reuse an existing provider when an ARN is explicitly supplied;
   - derives the Terraform state bucket as `lumi-terraform-state-<account-id>-<region>` when no override is provided;
   - provisions a rotating KMS key and encrypted/versioned S3 Terraform state bucket;
   - provisions `lumi-staging-github-deploy` and `lumi-production-github-deploy` roles with Environment-scoped OIDC subjects;
   - exports AWS account, region, state bucket, deploy role ARNs, and up to three available AZs;
   - contains the ECR repository/push/inspect permissions required for Terraform-managed runtime repositories and digest-preserving OCI promotion without `ecr:*`.

2. `scripts/aws_release_bootstrap_cloudshell.sh`
   - intended for one-time execution from an authenticated AWS CloudShell session;
   - validates the real AWS caller and Region before planning;
   - installs exactly Terraform `1.14.6` only when needed;
   - verifies the HashiCorp release archive with pinned SHA-256 for Linux AMD64/ARM64;
   - fetches and applies only the pinned bootstrap source commit `070315c2d3dd697bc87bc3a70acd7a3338175e40`;
   - refuses any bootstrap plan containing delete/replace actions;
   - is **plan-only by default** and requires `LUMI_BOOTSTRAP_APPLY=APPLY_AWS_BOOTSTRAP` for mutation;
   - stores the first bootstrap Terraform state into the newly created encrypted/versioned state bucket;
   - queries the target Region for PostgreSQL, Redis, and RabbitMQ capability candidates instead of guessing service versions;
   - emits `$HOME/lumi-aws-bootstrap-handoff.json` containing non-secret account/role/state/AZ metadata and Region capability candidates;
   - does **not** deploy Staging or Production application resources;
   - does **not** write GitHub secrets or GitHub Environment values automatically.

3. Hosted contract evidence on orchestration head `20da7ab01b515667585a8d91dc6cec46fdbeef5b` before this documentation-only commit:
   - Production IaC Contract run `32715176700`: **SUCCESS**;
   - Staging Release Ops Contract run `32715176775`: **SUCCESS**;
   - Runtime Image Closure Contract run `32715177078`: **SUCCESS**;
   - CodeQL run `32715176698`: **SUCCESS**;
   - Security Release Gate run `32715176799`: all substantive code/security jobs **SUCCESS** except the repository-level Dependency Review capability blocker.

## Remaining external boundary

No connected AWS execution capability is available to this ChatGPT session. Therefore the account-level bootstrap cannot be truthfully performed from the current tool boundary.

The next real infrastructure transition must start from an authenticated identity inside the target AWS account. Until that occurs, another `plan-core` dispatch would only repeat the same known precondition failure and must not be treated as progress.

After the AWS bootstrap is genuinely completed and the resulting Staging GitHub Environment configuration exists, the release sequence remains fail-closed:

1. rerun Staging `plan-core`;
2. inspect the emitted Terraform plan and require no destructive/replace data-layer actions;
3. only then run `apply-core` with explicit mutation acknowledgement;
4. promote the exact frozen six-runtime GHCR image set into Terraform-managed Staging ECR without rebuild and require digest preservation;
5. plan/apply migration and run the one-shot migration;
6. plan/apply App with the exact promoted six-image set;
7. collect real database/media/Tool Gateway/private-Model-Gateway evidence;
8. freeze and dispatch NODE-71 Staging Acceptance against runtime-image build run `32704633686` and RC SHA `3c6a95356a013c2bdf505bde14a7fcfcc33c32a9`.

## Verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

PR #135 remains Draft and must not be merged. The six-runtime RC build/freeze blocker is closed, but real NODE-71 Staging acceptance is still blocked at the AWS account bootstrap boundary.