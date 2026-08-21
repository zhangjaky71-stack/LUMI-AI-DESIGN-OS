# NODE-72 — Production Deployment & Infrastructure — Release Evidence

> Status: **SOURCE IMPLEMENTED / IMMUTABLE-GIT + DIGEST-PINNED BASE-IMAGE RC PROMOTION SOURCE-CLOSED / CLOUD VALIDATION PENDING / GO-LIVE BLOCKED**  
> Evidence date: 2026-08-21  
> Branch: `release-closure-p0`  
> Runtime supply-chain hardening baseline: `9cbfad30af4ead45401e72a01fa750928c0aff5d`  
> Latest sampled execution head: `9cbfad30af4ead45401e72a01fa750928c0aff5d`

## 1. Current decision

NODE-72 has a production deployment control plane and IaC source baseline. The source path from exact Git source plus digest-frozen runtime base inputs through an attested six-runtime NODE-71 image set to the NODE-72 Production gate is fail-closed, but **no real Production deployment has been proven**.

```text
SOURCE IMPLEMENTED
IMMUTABLE-GIT / BASE-IMAGE / ATTESTED RC PROMOTION CONTRACT: SOURCE-CLOSED
HOSTED EXECUTION: BLOCKED BEFORE STEPS START
CLOUD VALIDATION: PENDING
PRODUCTION: NOT PROVISIONED BY THIS EVIDENCE
GO-LIVE: BLOCKED
```

## 2. Exact RC runtime promotion chain

```text
exact release-closure-p0 Git SHA
→ six SHA-pinned remote Git contexts
→ resolve approved uv:0.11.28 + python:3.12-slim tags once
→ validate registry sha256 digests
→ inject one shared pair of digest-only UV_BASE_IMAGE / PYTHON_BASE_IMAGE refs into all six runtime builds
→ exact per-runtime Dockerfile + linux/amd64
→ BuildKit max SLSA v0.2 provenance
   repository.git#RC_SHA
   configSource.digest.sha1 == RC_SHA
   entryPoint == runtime Dockerfile
   platform == linux/amd64
   base-image build args == approved @sha256 refs
   materials include SHA-256 dependencies
→ immutable runtime registry digests + SPDX SBOM
→ GitHub artifact attestation
→ frozen container-image-set.json + attestation-verification.json
→ NODE-71 runtime-image binding
→ NODE-71 passed decision seal + decision provenance
→ NODE-72 Production deployment gate
→ exact NODE-71 accepted runtime digests passed to Terraform without rebuild
```

### 2.1 Immutable Git and base-image recipe binding

All six Dockerfiles now declare:

```text
ARG UV_BASE_IMAGE=ghcr.io/astral-sh/uv:0.11.28
ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${UV_BASE_IMAGE} AS uv
FROM ${PYTHON_BASE_IMAGE}
```

The defaults preserve local development ergonomics. Release builds are not allowed to rely on those mutable defaults: `.github/workflows/build-runtime-image-set.yml` resolves both tags once, requires valid registry `sha256` identities, exports digest-only refs, and passes the same pair to every build.

`scripts/validate_runtime_image_build_pipeline.py` requires every runtime independently to use:

- exact SHA-pinned remote Git context;
- exact service Dockerfile;
- `linux/amd64`;
- own immutable RC tag/build digest;
- shared `UV_BASE_IMAGE` and `PYTHON_BASE_IMAGE` env-derived build args;
- `provenance: mode=max,version=v0.2`;
- SPDX SBOM;
- own GitHub attestation and freeze fragment.

It rejects release regression to `context: .`, `{{defaultContext}}`, direct mutable `FROM` tags, a missing base resolver, a missing build arg, wrong Dockerfile/platform, or cross-wired digest/attestation/SBOM/provenance.

### 2.2 Actual provenance validation

`scripts/verify_runtime_image_attestations.py` requires live registry resolution plus canonical GitHub signer/source/ref/runner verification and validates actual BuildKit provenance:

```text
buildType == https://mobyproject.org/buildkit@v1
configSource.uri == https://github.com/<owner>/<repo>.git#<RC_SHA>
configSource.digest.sha1 == <RC_SHA>
configSource.entryPoint == <service Dockerfile>
invocation.environment.platform == linux/amd64
build-arg:UV_BASE_IMAGE == ghcr.io/astral-sh/uv@sha256:<64hex>
build-arg:PYTHON_BASE_IMAGE == python@sha256:<64hex>
materials != []
materials contain SHA-256 dependency identities
```

This makes the actual base-image inputs auditable in the same attestation report whose SHA-256 is frozen into the NODE-71 image set. The exact runtime image digest remains the promotion identity; Production is forbidden from rebuilding.

Sandbox `apt-get install ffmpeg` remains dependent on the package repository state at build time; the installed package set is expected in the actual image digest/SBOM. Fully snapshot-pinned OS repositories are not claimed here.

### 2.3 NODE-71 seal → NODE-72 gate

`validate_staging_runtime_image_binding.py`, `bind_node71_runtime_image_decision.py`, and `validate_node71_decision_artifact.py` bind exact build-run identity, report hash/source SHA, six runtime identities and decision seal into NODE-71. `production-deployment-gate.py` then revalidates the seal and requires Production images equal the NODE-71 accepted digests exactly.

## 3. Other Production source controls

NODE-72 also source-binds:

- exact NODE-71 decision/provenance and RC Git SHA/version/migration head;
- same Staging/Production Terraform module topology;
- `core -> Secret readiness -> pre-deploy snapshot -> migration -> app` ordering;
- private RDS PostgreSQL, Redis and RabbitMQ data planes;
- KMS/private/versioned S3;
- per-service ECS roles and Cloud Map;
- Route53/ACM/HTTPS/WAF edge;
- API canary + bake + alarm rollback;
- internal rolling/circuit-breaker deployments;
- one-shot Alembic migration and exit-code gate;
- GitHub Environment + OIDC Production mutation boundary;
- ECS steady-state and read-only Production smoke evidence contracts.

## 4. Current Hosted CI evidence

Sampled head: `9cbfad30af4ead45401e72a01fa750928c0aff5d`.

```text
Runtime Image Closure Contract
run_id: 32463049166
runtime-image-closure job_id: 96713773032
failure / logs_url=null / steps=null

Staging Acceptance Gate
run_id: 32463049198
source-contract job_id: 96713773436 -> failure / logs_url=null / steps=null
canonical-lock-gate job_id: 96713773525 -> failure / logs_url=null / steps=null
contract-gate job_id: 96713818623 -> failure / logs_url=null / steps=null
remote-read-only-preflight / acceptance-decision -> skipped

Production IaC Contract
run_id: 32463049236
terraform-static job_id: 96713773175 -> failure / logs_url=null / steps=null
source-contract job_id: 96713773407 -> failure / logs_url=null / steps=null
contract-gate job_id: 96713799231 -> failure / logs_url=null / steps=null

Final Product Acceptance Gate
run_id: 32463049209
canonical-lock-gate job_id: 96713773064 -> failure / logs_url=null / steps=null
source-contract job_id: 96713773267 -> failure / logs_url=null / steps=null
node73-final-contract-gate job_id: 96713812412 -> failure / logs_url=null / steps=null
final-decision -> skipped
```

These are zero-step Hosted-runner failures. No checkout, Python, `uv`, Docker, base-image digest resolution, registry attestation, Terraform, Staging or Production command is evidenced as having executed. They are neither source-contract failures nor PASS evidence.

## 5. Runtime evidence required before PASS

- [ ] Resolver-generated `uv.lock` contains all 17 workspace packages and frozen sync passes.
- [ ] Critical source/Terraform jobs actually execute with step/log evidence.
- [ ] Exact RC six-runtime build workflow executes from SHA-pinned Git context.
- [ ] Approved uv/Python tags resolve once and the exact shared digest-only refs are proven in all six provenance records.
- [ ] Six runtime registry digests, GitHub attestations, BuildKit provenance records and SPDX SBOMs verify.
- [ ] NODE-71 freezes the exact image-set/report artifact and emits a sealed `passed=true` decision.
- [ ] Production-like Staging is actually provisioned and all parity/Golden E2E/security/resilience/billing/performance/AI gates PASS.
- [ ] Production Terraform plan/apply, migration, canary, steady state and smoke PASS.
- [ ] Production consumes exact NODE-71 runtime digests without rebuild.
- [ ] Alarm rollback, post-promotion rollback and restore drills execute.
- [ ] Sandbox live restricted-egress and private Model Gateway deployed boundaries are proven.
- [ ] Durable Provider spend/idempotency semantics are proven against PostgreSQL/provider paths.

## 6. STOP SHIP

1. `uv.lock` remains stale by six workspace packages.
2. Hosted critical CI still fails before executable steps start.
3. No real base-image digest resolution or six-runtime registry build/attestation/SBOM/provenance artifact exists for the current RC.
4. NODE-71 has no real sealed `passed=true` Production-like Staging decision.
5. Production AWS resources/Secret Versions are not evidenced as provisioned.
6. PostgreSQL, Docker/runtime, Terraform, Staging E2E and Production smoke evidence remain missing.
7. Live Provider benchmark, canary/rollback/recovery and final approvals remain incomplete.

NODE-72 remains blocked until the exact NODE-71 accepted RC is proven by real runtime/cloud evidence and promoted without rebuild.