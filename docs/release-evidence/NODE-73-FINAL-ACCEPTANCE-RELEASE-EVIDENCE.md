# NODE-73 — Final Product Acceptance — Release Evidence

> Status: **SOURCE CLOSURE ADVANCED / IMMUTABLE-GIT + DIGEST-PINNED BASE-IMAGE RC PROMOTION SOURCE-CLOSED / FINAL PRODUCT NOT ACCEPTED / RUNTIME EVIDENCE PENDING**  
> Evidence date: 2026-08-21  
> Working branch: `release-closure-p0`  
> Runtime supply-chain hardening baseline: `9cbfad30af4ead45401e72a01fa750928c0aff5d`  
> Latest sampled execution head: `9cbfad30af4ead45401e72a01fa750928c0aff5d`  
> Draft PR: `#135 — release: close NODE-73 code-addressable P0 gates`

## 1. Current final decision

NODE-73 has a fail-closed source implementation for final product acceptance, and the current release-closure branch has source-closed multiple code-addressable P0 gaps. The LUMI release is still **not eligible for PRODUCT ACCEPTED status** because canonical dependency, Hosted CI, PostgreSQL, actual container build/attestation, Terraform, Staging, Production, live-provider, rollback and DR evidence remain incomplete.

# NOT ACCEPTED — SEE BLOCKING GAPS

## 2. Canonical dependency blocker

Final Acceptance requires all P0 PASS, no P0 `BLOCKED_EXTERNAL`/`DEFERRED`, no unresolved release blocker and all required upstream/approval gates PASS.

The root `uv.lock` remains stale by exactly six workspace packages:

```text
lumi-auth
lumi-domain
lumi-project-core
lumi-asset-storage
lumi-image-generation
lumi-video-generation
```

Canonical repair remains resolver-owned:

```text
uv lock
python3 scripts/validate_uv_workspace_lock.py
uv lock --check
uv sync --all-packages --frozen
```

`uv.lock` must not be hand-edited.

## 3. Code-addressable P0 source closure

### 3.1 Provider spend / durable paid effects

Provider attempt lifecycle, canonical NODE-27 ledger/reservations, platform spend stop and ambiguous-outcome fail-closed semantics are source-bound. Real PostgreSQL/provider execution remains required.

### 3.2 Sandbox production egress

Production IaC source separates general Internet-egress services from restricted Sandbox/outbox topology; Sandbox child execution retains `--network none`. Live network probes remain required.

### 3.3 Product image generation → Worker

Canonical source path is bound end-to-end:

```text
POST /generations
→ GenerationRuntimeGateway
→ ImageGenerationControlPlane
→ Generation + Task + image_generation_spec
→ job.dispatch.requested outbox
→ MediaJobOutboxDispatcher
→ image Worker routing
→ Worker Media image_transform
→ HostedImageGenerationRuntime
```

DB-only producer creation, durable publish ordering and Worker Hosted entrypoint are source-gated. PostgreSQL/real Worker execution remains pending.

### 3.4 Hosted Video cancellation truth

Cancellation is intent until Provider terminal truth. Source contracts preserve same-request reconciliation, Provider success winning races, transport-error recovery and no replacement paid request after cancellation intent. Hosted/PostgreSQL/live-provider proof remains pending.

### 3.5 Private Model Gateway

Provider model/media secrets are source-bound to `model-gateway`; Agent Runtime/Worker Media use private signed Gateway clients. Staging/Production IaC, ECS declared-secret materialization and runtime provenance are cross-layer gated. Deployed-task proof remains pending. This is not a claim that Agent/Worker have zero Internet egress.

### 3.6 P0-4 immutable runtime supply chain — Git source + base inputs + digest promotion

The current code-addressable chain is:

```text
exact release-closure-p0 Git SHA
→ six SHA-pinned remote Git contexts
→ resolve approved uv:0.11.28 + python:3.12-slim registry tags once
→ require sha256 identities
→ pass the same digest-only UV_BASE_IMAGE / PYTHON_BASE_IMAGE refs to all six Dockerfiles
→ exact service Dockerfile + linux/amd64
→ BuildKit max SLSA v0.2 provenance
   configSource.uri == repository.git#RC_SHA
   configSource.digest.sha1 == RC_SHA
   configSource.entryPoint == service Dockerfile
   invocation.environment.platform == linux/amd64
   build-arg:UV_BASE_IMAGE == ghcr.io/astral-sh/uv@sha256:...
   build-arg:PYTHON_BASE_IMAGE == python@sha256:...
   materials include SHA-256 dependencies
→ immutable runtime digest + SPDX SBOM
→ GitHub artifact attestation
   signer workflow + source SHA + release ref + hosted-runner identity
→ frozen image-set + attestation report
→ NODE-71 exact runtime-image binding
→ NODE-71 passed-decision seal + decision provenance
→ NODE-72 Production gate
→ exact accepted digests promoted without rebuild
```

#### Git source provenance

All six release images build from `https://github.com/${{ github.repository }}.git#${{ github.sha }}` rather than local `context: .`. `verify_runtime_image_attestations.py` requires actual BuildKit `configSource` repository/SHA/Dockerfile identity and platform, while `validate_runtime_image_build_pipeline.py` rejects regression to Path/default branch context or cross-wired digest/attestation/SBOM/freeze fragments.

#### Base-image immutability

All six Dockerfiles now expose the same two base-image parameters:

```text
ARG UV_BASE_IMAGE=ghcr.io/astral-sh/uv:0.11.28
ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${UV_BASE_IMAGE} AS uv
FROM ${PYTHON_BASE_IMAGE}
```

The tag defaults are local-development defaults only. The release workflow resolves each approved tag once to a registry digest, validates `sha256:<64hex>`, and supplies digest-only references to all six build steps. The max SLSA v0.2 provenance must record those build args, and the live verifier rejects a mutable value or unexpected base repository.

This removes a prior release-build ambiguity where the same Git SHA could resolve changed base-image bytes at different times. The actual runtime image digest remains the acceptance/promotion identity, and NODE-72 cannot rebuild.

Sandbox still installs `ffmpeg` from Debian repositories at build time. The final image digest and SPDX SBOM are expected to capture the resulting package set; fully snapshot-pinned OS repositories are not claimed and can be hardened separately.

#### NODE-71 / NODE-72 sealing

The attestation report is hash-bound into the frozen runtime set, NODE-71 downloads/verifies that exact artifact, a passed decision is resealed with the runtime binding, and NODE-72 revalidates the seal/report/source/build-run/six-runtime identity before Production promotion.

**Evidence boundary:** all of the above is source closure. No current RC six-image build, registry push, base-digest resolution, live provenance verification, Staging acceptance or Production promotion is claimed.

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

These are zero-step Hosted-runner failures. They are neither application/source-contract failures nor PASS evidence. No checkout, Python, `uv`, Docker, registry/base-image digest resolution, attestation, PostgreSQL, Terraform, Staging or Production command is evidenced as having executed.

## 5. Runtime evidence still required before PRODUCT ACCEPTED

### Dependency / CI

- [ ] Resolver-generated `uv.lock` covers all 17 workspace packages.
- [ ] exact workspace validation, `uv lock --check`, frozen all-workspace sync execute PASS.
- [ ] critical source/security/type/test workflows execute with real steps/logs.

### PostgreSQL / durable state

- [ ] migrations/ORM drift pass;
- [ ] Provider attempt/cost/idempotency hard-stop semantics pass against PostgreSQL;
- [ ] image producer and video recovery paths execute against PostgreSQL.

### Runtime supply chain

- [ ] canonical six-runtime build executes for the exact RC SHA remote Git context;
- [ ] approved uv/Python tags are resolved once and the same digest-only refs are proven in all six provenance records;
- [ ] six registry runtime digests resolve;
- [ ] six GitHub artifact attestations verify against canonical signer/source/ref/runner policy;
- [ ] six BuildKit provenance records prove exact repo/SHA/Dockerfile/platform/base args/materials;
- [ ] actual SPDX SBOMs are retrieved;
- [ ] exact image-set + attestation report is frozen from the exact build run;
- [ ] NODE-71 emits a real sealed `passed=true` decision;
- [ ] Production consumes those exact digests without rebuild;
- [ ] all packaged runtime entrypoints start and execute.

### Deployment / Provider / operations

- [ ] private Model Gateway secret/path boundary is proven on deployed tasks;
- [ ] Terraform plan/apply and Production-like Staging parity execute;
- [ ] Golden E2E/security/resilience/billing/performance/AI Staging gates PASS;
- [ ] Production migration/canary/steady-state/smoke/rollback PASS;
- [ ] live image/video Provider/model benchmarks are approved;
- [ ] NODE-66/68/69/70/71/72 required gates have real PASS evidence;
- [ ] final approvals and operational handoff are complete.

## 6. Current blocking facts

1. `uv.lock` is stale by six workspace packages.
2. Hosted critical CI still fails before executable steps start.
3. PostgreSQL runtime evidence is missing.
4. No actual base-image digest resolution or six-runtime registry build/attestation/SBOM/provenance artifact exists for the current RC.
5. No real NODE-71 sealed `passed=true` decision exists.
6. Model Gateway/Worker runtime start/execution proof is missing.
7. Terraform/Staging/Production proof is missing.
8. Private Gateway and canonical image/video paths are source-closed but not deployed-proven.
9. Live Provider benchmark approval is missing.
10. Canary/rollback/DR/final acceptance evidence remains incomplete.

Any one P0 blocker prevents PRODUCT ACCEPTED.

## 7. Completion rule

NODE-73 becomes COMPLETE only when one immutable release package produces:

```text
accepted=true
passed=true
headline="LUMI AI DESIGN OS — PRODUCT ACCEPTED"
blockers=[]
```

for the same exact accepted RC with all P0/upstream/deployment/approval evidence.

Until then:

# NOT ACCEPTED — SEE BLOCKING GAPS