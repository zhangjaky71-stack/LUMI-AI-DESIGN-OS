# NODE-71 — Staging End-to-End Acceptance — Release Evidence

> Evidence date: 2026-08-21  
> Branch: `release-closure-p0`  
> Runtime provenance hardening baseline: `9388984516602c3102d985797b51ad188b910bd9`  
> Latest sampled execution head: `9388984516602c3102d985797b51ad188b910bd9`  
> Status: **ACCEPTANCE HARNESS + STAGING IAC + IMMUTABLE-GIT RUNTIME ATTESTATION + RC DECISION SEAL SOURCE-CLOSED / STAGING RC NOT DEPLOYED / GO-LIVE BLOCKED**

## Decision

NODE-71 now has a fail-closed Staging acceptance control plane, production-like Staging IaC source definitions, a six-runtime supply-chain contract that binds the actual BuildKit source to the exact RC Git SHA, and a sealed decision/provenance path. This is **not** evidence that a Staging RC has been deployed or accepted.

No real Staging URL, successful six-runtime build, verified registry attestation artifact, completed environment parity proof, Golden E2E, resilience/security drills, browser matrix, NODE-69 launch run, NODE-70 production AI release decision, or final approver set has been evidenced for the current RC.

## Current repository reality

- Canonical Staging IaC exists under `infra/iac/environments/staging/` and shares the production-class module topology.
- Local Compose remains local-only and is not Staging evidence.
- Provider model/media secrets are source-bound to `model-gateway`; Agent Runtime and Worker Media use private Gateway URL + HMAC auth for Hosted model access.
- Staging Acceptance directly gates the private Model Gateway deployment contract.
- Root workspace and `uv.lock` still differ by exactly six packages: `lumi-auth`, `lumi-domain`, `lumi-project-core`, `lumi-asset-storage`, `lumi-image-generation`, `lumi-video-generation`.
- The lockfile must not be hand-edited and remains a frozen-install blocker.

## Source acceptance baseline

NODE-71 source controls include:

- versioned acceptance manifest and environment parity contract;
- synthetic account/evidence template;
- fail-closed `staging-acceptance-gate.py`;
- read-only HTTPS preflight;
- immutable evidence/live-producer binding;
- canonical dependency gate: `validate_uv_workspace_lock.py -> uv lock --check -> uv sync --all-packages --frozen`;
- private Model Gateway deployment boundary;
- exact runtime-image build/attestation binding;
- NODE-71 runtime-image decision seal and decision artifact provenance;
- canonical media-generation E2E and Tool Gateway provenance validators.

P0 still requires real evidenced PASS. `BLOCKED_EXTERNAL`, synthetic fixtures, source contracts, or local Compose cannot substitute for runtime acceptance.

## Attested runtime-image decision sealing — source-closed

The NODE-71 runtime-image acceptance path is now:

```text
exact RC Git SHA
→ six SHA-pinned remote Git build contexts
   https://github.com/${GITHUB_REPOSITORY}.git#${GITHUB_SHA}
→ exact per-runtime Dockerfile + linux/amd64
→ immutable registry digests
→ BuildKit max SLSA v0.2 provenance + SPDX SBOM
→ provenance source validation
   configSource.uri == repository.git#RC_SHA
   configSource.digest.sha1 == RC_SHA
   configSource.entryPoint == runtime Dockerfile
   invocation.environment.platform == linux/amd64
   materials != []
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

### Why the immutable Git context matters

The previous build recipe used `context: .`. That could prove which checked-out tree the workflow intended to use, but the BuildKit provenance validator itself accepted only the presence of a provenance object and did not require the provenance source to identify the exact repository, RC SHA, Dockerfile, platform, or even a non-empty material set.

The source contract now fails closed on that gap:

- `.github/workflows/build-runtime-image-set.yml` builds all six images from the exact Git SHA remote context rather than local Path context;
- every build pins `provenance: mode=max,version=v0.2` and `linux/amd64`;
- `scripts/verify_runtime_image_attestations.py` validates BuildKit `invocation.configSource` against the repository, exact RC SHA and service-specific Dockerfile, and requires non-empty materials;
- `scripts/validate_runtime_image_build_pipeline.py` rejects regression to `context: .`, `{{defaultContext}}`, wrong Dockerfile, missing Git auth, unpinned provenance shape, or missing per-runtime digest/attestation/SBOM/freeze binding.

This closes the code-addressable gap between “the static manifest says these files matter” and “the image provenance says which immutable Git source and Dockerfile actually built this digest.”

### Frozen build binding

`validate_staging_runtime_image_binding.py` requires the downloaded image-set artifact and attestation report to match:

- evidence RC SHA/version;
- frozen RC SHA/version;
- requested image-build run id;
- canonical GitHub build-run URL/repository;
- exact six image digests and provenance records;
- attestation report SHA-256;
- attestation `source_digest == RC git_sha`;
- consistent per-runtime signer/source policy.

The resulting `runtime-image-binding.json` carries:

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

### Decision sealing and provenance

`bind_node71_runtime_image_decision.py` accepts only a `passed=true` decision plus a valid runtime-image binding. It requires RC SHA/version/artifact-ref consistency, positive build-run identity, valid report hash, exact source SHA and six runtimes, then seals the binding into `decision.json` and recalculates `decision_id`.

`validate_node71_decision_artifact.py` refuses provenance creation or verification when a passed NODE-71 decision lacks the runtime-image seal, has an invalid field set, differs from the RC source SHA, or differs from the seal copied into decision provenance. An old-format unsealed `passed=true` decision therefore cannot satisfy the current NODE-71 artifact contract.

### Workflow anti-regression order

`validate_staging_runtime_image_workflow_contract.py` locks the acceptance order:

```text
immutable/live evidence binding
< exact image-set download
< runtime-image attestation binding
< Staging acceptance decision
< runtime-image decision seal
< decision provenance capture
< decision provenance self-verification
< artifact archive
```

## Hosted CI evidence — sampled hardening head

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
remote-read-only-preflight -> skipped on pull_request
acceptance-decision -> skipped on pull_request

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

These are zero-step Hosted-runner failures. They do not prove the new source contracts failed and they do not provide PASS evidence. No checkout, Python, `uv`, Docker, registry attestation, PostgreSQL, Terraform or Staging command is evidenced as having executed in those jobs.

## Acceptance coverage still requiring real execution

The acceptance manifest still requires real evidence across environment parity, synthetic tenant/account matrix, Golden brand-project E2E, precision edit invariants, agent/worker/provider/Redis/idempotency/DB resilience, cross-tenant/security/sandbox controls, billing/cost ledger, NODE-69 performance, NODE-70 AI release evidence, browser/IME/font/upload/download, data lifecycle, backup restore and observability correlation.

## Release blockers

- [ ] Resolver-generated `uv.lock` includes all 17 workspace packages and frozen validation passes.
- [ ] NODE-71 source/lock contracts actually execute with step/log evidence.
- [ ] Canonical six-runtime build workflow executes on the exact RC SHA.
- [ ] Six registry digests resolve and six GitHub artifact attestations verify.
- [ ] Each actual BuildKit provenance record proves the exact repository, RC SHA, runtime Dockerfile, `linux/amd64` and non-empty build materials.
- [ ] SPDX SBOMs are collected from the actual images.
- [ ] Frozen image-set + attestation report artifact is produced by the exact build run.
- [ ] Production-like Staging infrastructure is actually planned/applied and reachable.
- [ ] NODE-71 downloads the exact build artifact and emits a real sealed `passed=true` decision.
- [ ] All environment-parity, Golden E2E, security, resilience, billing, performance and AI checks have real PASS evidence.
- [ ] Canonical image/video producer → Worker → Provider → Artifact paths execute in Staging.
- [ ] Private Model Gateway secret/path boundary is proven on deployed tasks/images.
- [ ] Engineering/security/product/release-owner approvals are complete.

## Current status

```text
ACCEPTANCE MANIFEST: IMPLEMENTED SOURCE
ENVIRONMENT PARITY CONTRACT: IMPLEMENTED SOURCE
STAGING IAC: IMPLEMENTED SOURCE / NOT APPLIED
PRIVATE MODEL GATEWAY STAGING BINDING: SOURCE-CLOSED / DEPLOYED PROOF PENDING
RUNTIME IMAGE IMMUTABLE GIT SOURCE + ATTESTATION BINDING: SOURCE-CLOSED / ACTUAL BUILD MISSING
NODE-71 RUNTIME IMAGE DECISION SEAL: SOURCE-CLOSED / REAL SEALED DECISION MISSING
NODE-71 DECISION PROVENANCE: SOURCE-CLOSED / REAL PASSED ARTIFACT MISSING
CANONICAL LOCK: STALE / RESOLVER EXECUTION BLOCKED
HOSTED CI EXECUTION: BLOCKED BEFORE STEPS START
REAL STAGING RC: MISSING
REAL GOLDEN E2E / SECURITY / RESILIENCE / PERF / AI EVIDENCE: MISSING
FINAL APPROVALS: MISSING
NODE-71 GO-LIVE STATUS: BLOCKED
```

NODE-72 Production promotion may consume NODE-71 only after the exact immutable RC has a real, sealed and provenance-verified `passed=true` decision.