# NODE-72 — Production Deployment & Infrastructure — Release Evidence

> Status: **SOURCE IMPLEMENTED / IMMUTABLE-GIT ATTESTED RC PROMOTION SOURCE-CLOSED / CLOUD VALIDATION PENDING / GO-LIVE BLOCKED**  
> Evidence date: 2026-08-21  
> Branch: `release-closure-p0`  
> Runtime provenance hardening baseline: `9388984516602c3102d985797b51ad188b910bd9`  
> Latest sampled execution head: `9388984516602c3102d985797b51ad188b910bd9`

## 1. Current decision

NODE-72 has a production deployment control plane and IaC source baseline. The source path from an exact immutable Git source through an attested six-runtime NODE-71 image set to the NODE-72 Production gate is now fail-closed, but **no real Production deployment has been proven**.

A Terraform tree, frozen manifest, source validator, or zero-step CI run is not Production evidence. Production PASS still requires the exact NODE-71 accepted RC to be built, attested, deployed to production-like Staging, accepted, promoted without rebuild, provisioned, migrated, canaried, observed, smoke-tested and rollback-tested in the target cloud environment.

```text
SOURCE IMPLEMENTED
IMMUTABLE-GIT ATTESTED RC PROMOTION CONTRACT: SOURCE-CLOSED
HOSTED EXECUTION: BLOCKED BEFORE STEPS START
CLOUD VALIDATION: PENDING
PRODUCTION: NOT PROVISIONED BY THIS EVIDENCE
GO-LIVE: BLOCKED
```

## 2. Release identity and attested runtime promotion closure

The source chain is now:

```text
exact release-closure-p0 Git SHA
→ six SHA-pinned remote Git contexts
   https://github.com/${GITHUB_REPOSITORY}.git#${GITHUB_SHA}
→ exact per-runtime Dockerfile + linux/amd64
→ BuildKit max SLSA v0.2 provenance
   configSource URI == repository.git#RC_SHA
   configSource.digest.sha1 == RC_SHA
   configSource.entryPoint == runtime Dockerfile
   invocation.environment.platform == linux/amd64
   materials != []
→ immutable registry digests
→ SPDX SBOM
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

`scripts/validate_runtime_image_build_pipeline.py` binds every runtime independently. For each of:

```text
api
agent-runtime
model-gateway
tool-gateway
worker-media
sandbox-runtime
```

it requires:

- the correct Dockerfile;
- immutable remote Git context pinned to `${{ github.sha }}`;
- `linux/amd64`;
- immutable `rc-${GITHUB_SHA}` tag;
- `provenance: mode=max,version=v0.2`;
- scoped `GIT_AUTH_TOKEN` for Git context resolution;
- the runtime's own build-step digest;
- the runtime's own GitHub attestation subject/digest;
- the corresponding SBOM reference, provenance output and freeze fragment.

The validator rejects release-image regression to `context: .` or `{{defaultContext}}`. `.dockerignore` remains part of Runtime Image Closure so declared runtime source paths cannot be silently excluded from supported source topology.

### 2.2 Registry digest / attestation / actual BuildKit source binding

`scripts/verify_runtime_image_attestations.py` requires live registry resolution plus GitHub artifact attestation verification against:

- canonical signer workflow `.github/workflows/build-runtime-image-set.yml`;
- exact `GITHUB_SHA` source digest;
- exact `refs/heads/release-closure-p0` source ref;
- exact workflow ref;
- `--deny-self-hosted-runners`.

It also validates the actual BuildKit SLSA v0.2 provenance for each digest, rather than merely checking that a provenance object exists. The verifier requires:

```text
buildType == https://mobyproject.org/buildkit@v1
configSource.uri == https://github.com/<owner>/<repo>.git#<RC_SHA>
configSource.digest.sha1 == <RC_SHA>
configSource.entryPoint == <service Dockerfile>
invocation.environment.platform == linux/amd64
materials is a non-empty array
```

SPDX SBOM metadata is independently required. This closes the code-addressable gap where a workflow could previously have a valid GitHub attestation while the BuildKit provenance itself did not prove the exact immutable Git source/Dockerfile used for the image bytes.

`scripts/runtime_image_set.py` refuses to freeze an image set unless report `source_digest == frozen release_candidate.git_sha`, every runtime result carries the same signer/source policy, all six exact image digests are covered, and provenance/SBOM summaries are present.

### 2.3 NODE-71 sealed decision

`validate_staging_runtime_image_binding.py` cross-checks the downloaded frozen artifact, attestation report SHA-256, source digest, build repository/run identity, evidence RC SHA/version and exact six-runtime image/provenance set.

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

The sealer recalculates `decision_id`, so runtime-image attestation identity is inside the decision identity. `validate_node71_decision_artifact.py` refuses provenance creation or verification unless that seal exists and matches the NODE-71 release candidate.

### 2.4 NODE-72 direct promotion gate

`production-deployment-gate.py` rejects a NODE-71 decision when the runtime-image binding is missing or malformed; SHA/version differ from the Production RC; build run id is invalid; frozen artifact ref differs; attestation report hash/source digest is invalid; runtime count is not exactly six; or Production image digests differ from NODE-71 accepted image digests.

The normalized runtime-image seal contributes to the Production `gate_id`. `validate_production_deployment_contract.py` and `validate_production_node71_workflow_contract.py` independently lock those semantics.

## 3. Other Production source controls implemented

The NODE-72 source baseline also includes:

- exact NODE-71 decision/run/path and decision-provenance verification;
- same RC Git SHA, version and migration head;
- immutable digest-only images;
- Staging/Production same Terraform module topology;
- `core -> Secret readiness -> pre-deploy snapshot -> migration -> app` ordering;
- private RDS PostgreSQL, Redis and RabbitMQ data planes;
- KMS/private/versioned S3;
- per-service ECS task/execution roles and Cloud Map;
- Route53/ACM/HTTPS/WAF edge;
- API canary + bake + alarm rollback;
- rolling/circuit-breaker deployment for internal services;
- one-shot Alembic migration and exit-code gate;
- GitHub Environment + OIDC Production mutation boundary;
- ECS steady-state evidence and read-only Production smoke;
- provider spend hard-limit policy while durable Provider spend enforcement remains separately required from NODE-27/22 runtime evidence.

## 4. Current Hosted CI evidence

Sampled head: `9388984516602c3102d985797b51ad188b910bd9`.

```text
Runtime Image Closure Contract
run_id: 32462283655
runtime-image-closure job_id: 96711482008
failure / logs_url=null / steps=null

Staging Acceptance Gate
run_id: 32462283704
canonical-lock-gate job_id: 96711482611 -> failure / logs_url=null / steps=null
source-contract job_id: 96711482808 -> failure / logs_url=null / steps=null
contract-gate job_id: 96711514824 -> failure / logs_url=null / steps=null
remote-read-only-preflight -> skipped
acceptance-decision -> skipped

Production IaC Contract
run_id: 32462283621
terraform-static job_id: 96711482728 -> failure / logs_url=null / steps=null
source-contract job_id: 96711483040 -> failure / logs_url=null / steps=null
contract-gate job_id: 96711522020 -> failure / logs_url=null / steps=null

Final Product Acceptance Gate
run_id: 32462283662
source-contract job_id: 96711482533 -> failure / logs_url=null / steps=null
canonical-lock-gate job_id: 96711482731 -> failure / logs_url=null / steps=null
node73-final-contract-gate job_id: 96711498190 -> failure / logs_url=null / steps=null
final-decision -> skipped
```

These are zero-step Hosted-runner failures. No checkout, Python validator, runtime-image self-test, Terraform, `uv`, Docker, registry attestation, Staging or Production command is evidenced as having executed. They are **not evidence that the new contracts failed**, and they are **not PASS evidence**.

## 5. Runtime evidence required before PASS

### Canonical dependency / CI

- [ ] Resolver-generated root `uv.lock` includes all 17 workspace packages.
- [ ] `validate_uv_workspace_lock.py`, `uv lock --check`, and `uv sync --all-packages --frozen` execute and pass.
- [ ] Runtime Image Closure and Production IaC source/Terraform jobs actually execute with step/log evidence.

### Runtime images / attestations

- [ ] Canonical six-runtime build workflow executes from the exact RC SHA remote Git context.
- [ ] Six registry image digests are resolvable.
- [ ] Six GitHub artifact attestations verify against canonical signer/source/ref/runner policy.
- [ ] Six BuildKit provenance records prove exact repository, RC SHA, service Dockerfile, `linux/amd64` and non-empty materials.
- [ ] Six SPDX SBOMs are retrieved from the actual images.
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
.github/workflows/final-acceptance-gate.yml
scripts/verify_runtime_image_attestations.py
scripts/runtime_image_set.py
scripts/validate_runtime_image_build_pipeline.py
scripts/validate_runtime_image_set_contract.py
scripts/validate_staging_runtime_image_binding.py
scripts/bind_node71_runtime_image_decision.py
scripts/validate_node71_decision_artifact.py
scripts/production-deployment-gate.py
scripts/validate_production_deployment_contract.py
scripts/validate_production_node71_workflow_contract.py
```

NODE-72 remains blocked until the exact NODE-71 accepted RC is proven by real runtime/cloud evidence and promoted without rebuild.