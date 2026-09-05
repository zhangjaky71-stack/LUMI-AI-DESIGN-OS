# NODE-71 — Staging End-to-End Acceptance — Release Evidence

> Evidence date: 2026-08-21  
> Branch: `release-closure-p0`  
> Runtime supply-chain hardening baseline: `9cbfad30af4ead45401e72a01fa750928c0aff5d`  
> Latest sampled execution head: `9cbfad30af4ead45401e72a01fa750928c0aff5d`  
> Status: **ACCEPTANCE HARNESS + STAGING IAC + IMMUTABLE-GIT/BASE-IMAGE ATTESTATION + RC DECISION SEAL SOURCE-CLOSED / STAGING RC NOT DEPLOYED / GO-LIVE BLOCKED**

## Decision

NODE-71 has a fail-closed Staging acceptance control plane, production-like Staging IaC source definitions, private Model Gateway deployment contracts, and a six-runtime supply-chain path that binds both the exact RC Git source and the resolved runtime base-image inputs into actual BuildKit provenance. This is **not** evidence that a Staging RC has been deployed or accepted.

No real Staging URL, successful six-runtime build, registry attestation artifact, environment parity proof, Golden E2E, resilience/security drills, browser matrix, performance/AI release evidence, or final approver set has been produced for the current RC.

## Current repository reality

- Canonical Staging IaC exists under `infra/iac/environments/staging/`; source IaC absence is not the current blocker.
- Local Compose is not Staging evidence.
- Provider model/media secrets are source-bound to `model-gateway`; Agent Runtime and Worker Media use private Gateway URL + HMAC auth for Hosted model access.
- Root workspace and `uv.lock` still differ by exactly six packages: `lumi-auth`, `lumi-domain`, `lumi-project-core`, `lumi-asset-storage`, `lumi-image-generation`, `lumi-video-generation`.
- `uv.lock` must not be hand-edited; canonical resolver/frozen-sync execution remains blocked.

## Source acceptance baseline

NODE-71 source controls include:

- versioned acceptance manifest and environment parity contract;
- synthetic account/evidence template and fail-closed acceptance decision;
- read-only HTTPS preflight;
- immutable evidence/live-producer binding;
- canonical dependency gate: `validate_uv_workspace_lock.py -> uv lock --check -> uv sync --all-packages --frozen`;
- private Model Gateway deployment boundary;
- exact runtime-image Git/base-image build/attestation binding;
- NODE-71 runtime-image decision seal and decision artifact provenance;
- canonical media-generation E2E and Tool Gateway provenance validators.

P0 still requires real evidenced PASS. Synthetic fixtures, source contracts, `BLOCKED_EXTERNAL`, or local Compose cannot substitute for runtime acceptance.

## Attested runtime-image decision sealing — source-closed

The NODE-71 runtime-image path is now:

```text
exact RC Git SHA
→ six SHA-pinned remote Git contexts
   https://github.com/${GITHUB_REPOSITORY}.git#${GITHUB_SHA}
→ resolve uv:0.11.28 and python:3.12-slim once to registry @sha256 identities
→ inject the same UV_BASE_IMAGE / PYTHON_BASE_IMAGE digest-only build args into all six Dockerfiles
→ exact per-runtime Dockerfile + linux/amd64
→ immutable registry image digest
→ BuildKit max SLSA v0.2 provenance + SPDX SBOM
→ provenance validation
   configSource.uri == repository.git#RC_SHA
   configSource.digest.sha1 == RC_SHA
   configSource.entryPoint == runtime Dockerfile
   invocation.environment.platform == linux/amd64
   build-arg:UV_BASE_IMAGE == ghcr.io/astral-sh/uv@sha256:...
   build-arg:PYTHON_BASE_IMAGE == python@sha256:...
   materials contains immutable SHA-256 dependencies
→ GitHub artifact attestation
   signer workflow + source SHA + release ref + hosted-runner identity
→ container-image-set.json + attestation-verification.json
→ NODE-71 exact runtime-image binding
→ staging-acceptance decision
→ runtime_image_binding seal
→ resealed decision_id
→ decision SHA-256 workflow provenance
→ archive
```

### Immutable source and base-image inputs

The earlier release recipe had two supply-chain weaknesses that are now code-addressed:

1. local `context: .` did not make BuildKit itself prove the exact Git repository/revision in trusted `configSource`;
2. Dockerfiles directly used mutable `ghcr.io/astral-sh/uv:0.11.28` and `python:3.12-slim` `FROM` tags, so the same Git SHA could resolve different base image bytes in separate build runs.

Current source hardening:

- `.github/workflows/build-runtime-image-set.yml` builds from the exact remote Git SHA;
- the release build resolves both approved base tags once, validates registry digests as `sha256:<64 hex>`, then exports digest-only image refs;
- all six Dockerfiles accept `UV_BASE_IMAGE` and `PYTHON_BASE_IMAGE` build args and consume those variables in `FROM`;
- every release build receives the same two resolved digest-only values;
- `provenance: mode=max,version=v0.2` records build-arg values and materials;
- `scripts/verify_runtime_image_attestations.py` rejects mutable base tags, unexpected base repositories, wrong Git source/Dockerfile/platform, empty materials, or materials with no SHA-256 dependencies;
- `scripts/validate_runtime_image_build_pipeline.py` rejects any runtime Dockerfile/workflow regression that bypasses the shared digest resolver or the immutable Git/base-image inputs.

The default tag-valued ARGs remain only for local developer ergonomics. **Release builds are statically required to override them with digest-only refs**, and the actual provenance must prove those override values.

Sandbox still installs `ffmpeg` via Debian package repositories; the actual installed package set is expected to be captured by the final image digest and SPDX SBOM. Fully snapshot-pinning OS package repositories is not claimed by this source closure and remains a reproducibility-hardening opportunity, not a substitute for current P0 runtime evidence.

### Frozen build / decision binding

`validate_staging_runtime_image_binding.py` cross-checks the frozen image-set artifact, attestation report bytes/hash/source digest, build repository/run identity, evidence RC SHA/version and exact six image/provenance records.

`bind_node71_runtime_image_decision.py` accepts only a passed NODE-71 decision plus valid runtime-image binding, seals the exact runtime binding into `decision.json`, and recalculates `decision_id`. `validate_node71_decision_artifact.py` refuses provenance creation/verification for an unsealed, malformed or source-SHA-mismatched passed decision.

The acceptance order remains fail-closed:

```text
immutable/live evidence binding
< image-set download
< runtime-image attestation binding
< Staging acceptance decision
< runtime-image decision seal
< decision provenance capture
< provenance self-verification
< artifact archive
```

## Hosted CI evidence — current sampled head

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
remote-read-only-preflight -> skipped
acceptance-decision -> skipped

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

These are zero-step Hosted-runner failures. They neither prove the new contracts failed nor provide PASS evidence. No checkout, Python, `uv`, Docker, base-image digest resolution, registry attestation, PostgreSQL, Terraform or Staging command is evidenced as having executed.

## Release blockers

- [ ] Resolver-generated `uv.lock` includes all 17 workspace packages and frozen validation passes.
- [ ] NODE-71 source/lock contracts actually execute with step/log evidence.
- [ ] Canonical six-runtime workflow executes on the exact RC SHA.
- [ ] Approved uv/Python base tags resolve once and the same digest-only refs are proven in all six actual provenance records.
- [ ] Six registry image digests resolve and six GitHub artifact attestations verify.
- [ ] Each actual BuildKit provenance proves exact repository, RC SHA, runtime Dockerfile, `linux/amd64`, immutable base-image build args and SHA-256 materials.
- [ ] Actual SPDX SBOMs are retrieved and frozen.
- [ ] Production-like Staging infrastructure is actually applied and reachable.
- [ ] NODE-71 downloads the exact build artifact and emits a real sealed `passed=true` decision.
- [ ] Environment-parity, Golden E2E, security, resilience, billing, performance and AI checks have real PASS evidence.
- [ ] Canonical image/video producer → Worker → Provider → Artifact paths execute in Staging.
- [ ] Private Model Gateway boundary is proven on deployed tasks/images.
- [ ] Engineering/security/product/release-owner approvals are complete.

## Current status

```text
ACCEPTANCE HARNESS: IMPLEMENTED SOURCE
STAGING IAC: IMPLEMENTED SOURCE / NOT APPLIED
PRIVATE MODEL GATEWAY STAGING BINDING: SOURCE-CLOSED / DEPLOYED PROOF PENDING
RUNTIME IMAGE IMMUTABLE GIT SOURCE: SOURCE-CLOSED / ACTUAL BUILD MISSING
RUNTIME IMAGE DIGEST-PINNED UV/PYTHON BASE INPUTS: SOURCE-CLOSED / ACTUAL RESOLUTION+PROVENANCE MISSING
NODE-71 RUNTIME IMAGE DECISION SEAL: SOURCE-CLOSED / REAL SEALED DECISION MISSING
CANONICAL LOCK: STALE / RESOLVER EXECUTION BLOCKED
HOSTED CI EXECUTION: BLOCKED BEFORE STEPS START
REAL STAGING RC: MISSING
REAL GOLDEN E2E / SECURITY / RESILIENCE / PERF / AI EVIDENCE: MISSING
FINAL APPROVALS: MISSING
NODE-71 GO-LIVE STATUS: BLOCKED
```

NODE-72 Production promotion may consume NODE-71 only after the exact immutable RC has a real, sealed and provenance-verified `passed=true` decision.