# NODE-71 — Staging End-to-End Acceptance — Release Evidence

> Evidence date: 2026-08-21  
> Branch: `release-closure-p0`  
> Current source head: `6a52e5b5f44a86e8b7360c165242c0e02f013351`  
> Latest sampled execution head: `29602f4d0f5117f174ae4f4c806145c420635050`  
> Status: **ACCEPTANCE HARNESS + STAGING IAC + ATTESTED RC DECISION SEAL SOURCE-CLOSED / STAGING RC NOT DEPLOYED / GO-LIVE BLOCKED**

## Decision

NODE-71 has a fail-closed Staging acceptance control plane, production-like Staging IaC source definitions, exact six-runtime image/attestation binding, and a sealed decision/provenance path. This is **not** evidence that a Staging RC has been deployed or accepted.

No real Staging URL, executed six-runtime image build, verified registry attestation artifact, completed environment parity proof, Golden E2E, resilience/security drills, browser matrix, NODE-69 launch run, NODE-70 production AI release decision, or final approver set has been evidenced for the current RC.

## Current repository reality

- Canonical Staging IaC exists under `infra/iac/environments/staging/` and shares the production-class module topology.
- Local Compose remains local-only and is not Staging evidence.
- Provider model/media secrets are source-bound to `model-gateway`; Agent Runtime and Worker Media use private Gateway URL + HMAC auth for Hosted model access.
- Staging Acceptance directly gates the private Model Gateway deployment contract.
- Root workspace and `uv.lock` still differ by exactly six packages: `lumi-auth`, `lumi-domain`, `lumi-project-core`, `lumi-asset-storage`, `lumi-image-generation`, `lumi-video-generation`.
- The lockfile must not be hand-edited and remains a frozen-install blocker.

## Source acceptance baseline

NODE-71 source controls include:

- versioned 30-scenario acceptance manifest and environment parity contract;
- synthetic account/evidence template;
- fail-closed `staging-acceptance-gate.py`;
- read-only HTTPS preflight;
- immutable evidence/live-producer binding;
- canonical dependency gate: `validate_uv_workspace_lock.py -> uv lock --check -> uv sync --all-packages --frozen`;
- private Model Gateway deployment boundary;
- exact runtime-image build/attestation binding;
- NODE-71 decision artifact workflow provenance;
- canonical media-generation E2E and Tool Gateway provenance validators.

P0 still requires real evidenced PASS. `BLOCKED_EXTERNAL`, synthetic fixtures, source contracts, or local Compose cannot substitute for runtime acceptance.

## Attested runtime-image decision sealing — source-closed

The NODE-71 runtime-image acceptance path is now:

```text
exact RC Git SHA
→ six exact runtime Dockerfile builds
→ immutable registry digests
→ BuildKit max provenance + SPDX SBOM
→ GitHub artifact attestation bound to signer/source SHA/ref/runner policy
→ container-image-set.json + attestation-verification.json
→ NODE-71 exact runtime-image binding
→ staging-acceptance decision
→ runtime_image_binding seal
→ resealed decision_id
→ decision SHA-256 workflow provenance
→ archive
```

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

### Decision sealing

`bind_node71_runtime_image_decision.py` accepts only a `passed=true` decision plus a valid runtime-image binding. It requires RC SHA/version/artifact-ref consistency, positive build-run identity, valid report hash, exact source SHA and six runtimes, then:

- adds the normalized `runtime_image_binding` to `decision.json`;
- recalculates `decision_id` over the sealed decision;
- updates the human decision Markdown with the new Decision ID and attestation PASS seal.

### Decision provenance

`validate_node71_decision_artifact.py` now refuses both provenance creation and provenance verification when a passed NODE-71 decision:

- lacks the runtime-image seal;
- has an invalid seal field set;
- has a source SHA different from the RC;
- has invalid build-run/hash/count identity;
- differs from the seal copied into decision provenance.

Therefore an old-format unsealed `passed=true` decision cannot satisfy the current NODE-71 artifact contract.

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

The archived runtime directory includes the evidence binding, `runtime-image-binding.json`, sealed `decision.json`, decision Markdown and decision provenance.

## Acceptance coverage still requiring real execution

The manifest includes P0/P1 coverage for:

```text
Environment parity
Synthetic tenant/account matrix
Golden brand-project E2E
Precision edit invariants
Agent/worker/provider/Redis/idempotency/DB resilience
Cross-tenant, signed URL, SVG, prompt injection, SSRF, sandbox, admin/approval security
Cost ledger / budget / credits / webhook idempotency
NODE-69 performance launch profile
NODE-70 production-candidate AI release evidence
Chrome / Edge / Safari
Chinese IME / fonts / upload / download
Project/archive/data retention/vector/audit/export expiry
Backup restore
Observability correlation
```

## Hosted CI evidence

The latest sampled critical execution evidence is from head `29602f4d0f5117f174ae4f4c806145c420635050`.

```text
Runtime Image Closure
run_id: 32459558295
runtime-image-closure job_id: 96703575372
failure / logs_url=null / steps=null

Production IaC Contract
run_id: 32459558285
terraform-static job_id: 96703575564 -> failure / logs_url=null / steps=null
source-contract job_id: 96703575742 -> failure / logs_url=null / steps=null
contract-gate job_id: 96703588716 -> failure / logs_url=null / steps=null

Final Product Acceptance
run_id: 32459558476
source-contract job_id: 96703576056 -> failure / logs_url=null / steps=null
canonical-lock-gate job_id: 96703576351 -> failure / logs_url=null / steps=null
node73-final-contract-gate job_id: 96703611450 -> failure / logs_url=null / steps=null
final-decision -> skipped
```

These are zero-step Hosted-runner failures. They do not prove the source contracts failed and they do not provide PASS evidence. No checkout, Python, `uv`, Docker, registry attestation, PostgreSQL, Terraform or Staging command is evidenced as having executed in these jobs.

## Release blockers

- [ ] Resolver-generated `uv.lock` includes all 17 workspace packages and frozen validation passes.
- [ ] NODE-71 source/lock contracts actually execute with step/log evidence.
- [ ] Canonical six-runtime build workflow executes on the exact RC SHA.
- [ ] Six registry digests resolve and six GitHub artifact attestations verify.
- [ ] BuildKit provenance and SPDX SBOMs are collected from the actual images.
- [ ] Frozen image-set + attestation report artifact is produced by the exact build run.
- [ ] Production-like Staging infrastructure is actually planned/applied and reachable.
- [ ] NODE-71 downloads the exact build artifact and emits a real sealed `passed=true` decision.
- [ ] All environment-parity checks have real PASS evidence.
- [ ] Synthetic Org A/B/ops/billing accounts are provisioned without production customer data.
- [ ] Read-only remote preflight passes on the exact RC.
- [ ] Golden Brand Project and Precision Edit E2Es pass.
- [ ] Canonical image/video producer → Worker → Provider → Artifact paths execute in Staging.
- [ ] Private Model Gateway secret/path boundary is proven on deployed tasks/images.
- [ ] Resilience/security/billing/performance/AI gates execute and pass.
- [ ] Browser/IME/font/upload/download and data-lifecycle/recovery/observability evidence pass.
- [ ] Engineering/security/product/release-owner approvals are complete.

## Current status

```text
ACCEPTANCE MANIFEST: IMPLEMENTED SOURCE
ENVIRONMENT PARITY CONTRACT: IMPLEMENTED SOURCE
STAGING IAC: IMPLEMENTED SOURCE / NOT APPLIED
PRIVATE MODEL GATEWAY STAGING BINDING: SOURCE-CLOSED / DEPLOYED PROOF PENDING
RUNTIME IMAGE BUILD/ATTESTATION BINDING: SOURCE-CLOSED / ACTUAL BUILD MISSING
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