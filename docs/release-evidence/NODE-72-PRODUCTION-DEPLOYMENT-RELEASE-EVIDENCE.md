# NODE-72 — Production Deployment & Infrastructure — Release Evidence

> Status: **SOURCE IMPLEMENTED / ATTESTED RC PROMOTION SOURCE-CLOSED / CLOUD VALIDATION PENDING / GO-LIVE BLOCKED**  
> Evidence date: 2026-08-21  
> Branch: `release-closure-p0`  
> Current sampled head: `29602f4d0f5117f174ae4f4c806145c420635050`

## 1. Current decision

NODE-72 has a production deployment control plane and IaC source baseline. The source path from an attested six-runtime NODE-71 image build to the NODE-72 Production gate is now fail-closed, but **no real Production deployment has been proven**.

A Terraform tree, a frozen manifest, or a source validator is not Production evidence. Production PASS still requires the exact NODE-71 accepted RC to be built, attested, deployed to production-like Staging, accepted, promoted without rebuild, provisioned, migrated, canaried, observed, smoke-tested and rollback-tested in the target cloud environment.

```text
SOURCE IMPLEMENTED
ATTESTED RC PROMOTION CONTRACT: SOURCE-CLOSED
HOSTED EXECUTION: BLOCKED BEFORE STEPS START
CLOUD VALIDATION: PENDING
PRODUCTION: NOT PROVISIONED BY THIS EVIDENCE
GO-LIVE: BLOCKED
```

## 2. Release identity and attested runtime promotion closure

The source chain is now:

```text
exact release-closure-p0 Git SHA
→ six exact runtime Dockerfile/build blocks
→ root build context + .dockerignore provenance-source guard
→ immutable registry digests
→ BuildKit max provenance + SPDX SBOM
→ GitHub artifact attestation
   signer workflow + source SHA + release ref + hosted-runner identity
→ frozen container-image-set.json + attestation-verification.json
→ NODE-71 runtime-image binding
→ NODE-71 passed decision runtime_image_binding seal
→ NODE-71 decision SHA-256 workflow provenance
→ NODE-72 Production deployment gate
→ exact six accepted image digests passed to Terraform
```

### 2.1 Exact per-runtime build identity

`scripts/validate_runtime_image_build_pipeline.py` now binds every runtime independently rather than relying only on six global counts. For each of:

```text
api
agent-runtime
model-gateway
tool-gateway
worker-media
sandbox-runtime
```

it requires the correct Dockerfile, root context, `linux/amd64`, immutable `rc-${GITHUB_SHA}` tag, the runtime's own build-step digest, the runtime's own GitHub attestation step, the corresponding SBOM reference, provenance output, and freeze fragment.

`.dockerignore` is now part of the Runtime Image Closure trigger and the source contract fails closed if a positive ignore rule can remove a runtime `source_paths` entry declared by `production/runtime-images/manifest-v1.json`.

### 2.2 Registry digest / attestation / source SHA binding

`scripts/verify_runtime_image_attestations.py` already requires live registry resolution plus GitHub artifact attestation verification against:

- canonical signer workflow `.github/workflows/build-runtime-image-set.yml`;
- exact `GITHUB_SHA` source digest;
- exact `refs/heads/release-closure-p0` source ref;
- exact workflow ref;
- `--deny-self-hosted-runners`;
- actual BuildKit provenance metadata;
- actual SPDX SBOM metadata.

`scripts/runtime_image_set.py` now additionally refuses to freeze an image set unless:

- report `github_attestation_policy.source_digest == frozen release_candidate.git_sha`;
- every runtime result carries the same signer/source policy as the report-level policy;
- all six exact image digests are covered;
- all six registry digests and GitHub attestations report PASS;
- BuildKit provenance and SBOM summaries are present.

The frozen metadata now includes `source_digest` alongside the attestation report SHA-256.

### 2.3 NODE-71 sealed decision

`validate_staging_runtime_image_binding.py` now cross-checks the downloaded frozen artifact, attestation report SHA-256, source digest, build repository/run identity, evidence RC SHA/version and exact six-runtime image/provenance set.

`bind_node71_runtime_image_decision.py` then seals the verified result into the passed NODE-71 decision as the exact field set:

```text
status
 git_sha
 version
 build_run_id
 container_image_set_ref
 attestation_report_sha256
 attestation_source_digest
 runtime_count
```

The sealer recalculates `decision_id`, so runtime-image attestation identity is inside the decision identity rather than being a side file only. The human decision Markdown is updated to the resealed decision ID.

`validate_node71_decision_artifact.py` now refuses both provenance creation and provenance verification unless this runtime-image seal exists and matches the NODE-71 release candidate. Decision provenance copies the seal as well as hashing the complete sealed `decision.json`.

The NODE-71 workflow contract locks the required order:

```text
live staging evidence binding
< frozen image-set download
< runtime-image attestation binding
< staging acceptance decision
< runtime-image decision seal
< decision provenance capture
< provenance self-verification
< artifact archive
```

### 2.4 NODE-72 direct promotion gate

`production-deployment-gate.py` no longer checks only the six accepted digest strings. It directly rejects a NODE-71 decision when:

- `runtime_image_binding` is absent or not exactly shaped;
- binding status is not PASS;
- binding SHA/version differ from the Production RC;
- runtime image build run id is not a positive GitHub Actions run id;
- frozen image-set artifact ref differs from NODE-71 RC identity;
- attestation report SHA-256 is malformed;
- attestation source digest differs from the Production RC SHA;
- runtime count is not exactly six;
- Production image digests differ from NODE-71 accepted image digests.

The normalized runtime-image seal is included in the Production gate payload and therefore in `gate_id`.

`validate_production_deployment_contract.py` contains negative drills for missing seal, source-SHA swap, invalid build run, invalid report hash, artifact-ref swap and unexpected seal fields. `validate_production_node71_workflow_contract.py` independently locks the NODE-71 sealer interlock and the NODE-72 promotion checks.

## 3. Other Production source controls implemented

The existing NODE-72 source baseline also includes:

- exact NODE-71 decision/run/path and decision-provenance verification;
- same RC Git SHA, version and migration head;
- immutable digest-only images;
- Staging/Production same Terraform module topology;
- `core -> Secret readiness -> pre-deploy snapshot -> migration -> app` ordering;
- private RDS PostgreSQL, Redis and RabbitMQ data planes;
- KMS/private/versioned S3;
- per-service ECS task/execution roles and Cloud Map;
- Route53/ACM/HTTPS/WAF edge;
- API 5% ECS-native canary + bake + alarm rollback;
- rolling/circuit-breaker deployment for internal services;
- one-shot Alembic migration and exit-code gate;
- GitHub Environment + OIDC Production mutation boundary;
- ECS steady-state evidence and read-only Production smoke;
- first-day provider spend hard limit <= $100 in the release manifest, while durable Provider spend enforcement remains separately required from NODE-27/22 runtime evidence.

## 4. Current Hosted CI evidence

Sampled head: `29602f4d0f5117f174ae4f4c806145c420635050`.

### Runtime Image Closure

```text
run_id: 32459558295
runtime-image-closure job_id: 96703575372
conclusion: failure
logs_url: null
steps: null
```

### Production IaC Contract

```text
run_id: 32459558285
terraform-static job_id: 96703575564 -> failure, logs_url=null, steps=null
source-contract job_id: 96703575742 -> failure, logs_url=null, steps=null
contract-gate job_id: 96703588716 -> failure, logs_url=null, steps=null
```

### Final Product Acceptance Gate

```text
run_id: 32459558476
source-contract job_id: 96703576056 -> failure, logs_url=null, steps=null
canonical-lock-gate job_id: 96703576351 -> failure, logs_url=null, steps=null
node73-final-contract-gate job_id: 96703611450 -> failure, logs_url=null, steps=null
final-decision -> skipped
```

These are the same zero-step Hosted-runner failures seen on prior heads. No checkout, Python validator, runtime-image self-test, Terraform, `uv`, Docker, registry attestation, Staging or Production command is evidenced as having executed in those jobs. They are **not evidence that the new contracts failed**, and they are **not PASS evidence**.

## 5. Runtime evidence required before PASS

All remain unchecked until actual execution produces immutable evidence.

### Canonical dependency / CI

- [ ] Resolver-generated root `uv.lock` includes all 17 workspace packages.
- [ ] `validate_uv_workspace_lock.py`, `uv lock --check`, and `uv sync --all-packages --frozen` execute and pass.
- [ ] Runtime Image Closure and Production IaC source/Terraform jobs actually execute with step/log evidence.

### Runtime images / attestations

- [ ] Canonical six-runtime build workflow executes from the exact RC SHA.
- [ ] Six registry image digests are resolvable.
- [ ] Six GitHub artifact attestations verify against the canonical signer workflow, exact source SHA/ref and hosted-runner policy.
- [ ] Six BuildKit provenance records and SPDX SBOMs are retrieved from the actual images.
- [ ] `container-image-set.json` and `attestation-verification.json` are frozen and archived from that exact build run.
- [ ] NODE-71 downloads that exact build artifact and emits a sealed `passed=true` decision.
- [ ] Production consumes the exact NODE-71 accepted digests without rebuilding them.

### Staging / cloud / Production

- [ ] Production-like Staging infrastructure is actually applied and reachable.
- [ ] NODE-71 environment parity, Golden E2E, security, resilience, billing, performance and AI gates all PASS for the exact RC.
- [ ] Production Terraform plan/apply succeeds in the approved AWS account.
- [ ] Secret Versions/provider quotas/DNS/TLS/billing/email/support dependencies are ready.
- [ ] One-shot migration, canary, ECS steady state and Production smoke pass.
- [ ] Alarm rollback and post-promotion rollback are actually exercised.
- [ ] NODE-68 recovery/restore and NODE-69 capacity evidence meet release policy.
- [ ] Sandbox production egress and private Model Gateway deployed boundaries are proven live.
- [ ] Durable platform Provider spend hard stop and no-duplicate-paid-effect semantics are proven against PostgreSQL/provider paths.

## 6. Current STOP SHIP list

1. `uv.lock` remains stale by six workspace packages and has not been resolver-regenerated.
2. Hosted critical CI still fails before executable steps start.
3. No real six-runtime registry build/attestation/SBOM/provenance artifact exists for the current RC.
4. NODE-71 has no real sealed `passed=true` Production-like Staging decision.
5. Production AWS resources and real Secret Versions are not evidenced as provisioned.
6. Real PostgreSQL, Docker/runtime, Terraform plan/apply, Staging E2E and Production smoke evidence remain missing.
7. Live Provider image/video benchmark evidence for production-routed profiles remains incomplete.
8. Canary/rollback/recovery drills and final Production approvals remain incomplete.

## 7. Evidence locations

```text
production/runtime-images/manifest-v1.json
.github/workflows/build-runtime-image-set.yml
.github/workflows/runtime-image-closure-contract.yml
.github/workflows/staging-acceptance-gate.yml
.github/workflows/deploy-production.yml
.github/workflows/production-iac-contract.yml
scripts/verify_runtime_image_attestations.py
scripts/runtime_image_set.py
scripts/validate_runtime_image_build_pipeline.py
scripts/validate_runtime_image_set_contract.py
scripts/validate_staging_runtime_image_binding.py
scripts/bind_node71_runtime_image_decision.py
scripts/validate_staging_runtime_image_workflow_contract.py
scripts/validate_node71_decision_artifact.py
scripts/production-deployment-gate.py
scripts/validate_production_deployment_contract.py
scripts/validate_production_node71_workflow_contract.py
infra/iac/
reports/production-deployments/
```

## 8. Completion rule

NODE-72 may move to COMPLETE only when:

```text
canonical dependencies resolved
+ exact six-runtime registry images built and attestations/SBOM/provenance verified
+ same immutable image set accepted by real NODE-71 Staging decision
+ same digests promoted to Production without rebuild
+ Production infrastructure provisioned through controlled CI/CD
+ migration/canary/smoke/SLO green
+ rollback/recovery/security/cost controls proven
```

Until then:

**SOURCE IMPLEMENTED / ATTESTED RC PROMOTION SOURCE-CLOSED / CLOUD VALIDATION PENDING / GO-LIVE BLOCKED**.
