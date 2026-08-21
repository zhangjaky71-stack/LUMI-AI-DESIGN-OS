# NODE-73 — Final Product Acceptance — Release Evidence

> Status: **SOURCE CLOSURE ADVANCED / ATTESTED RC PROMOTION SOURCE-CLOSED / FINAL PRODUCT NOT ACCEPTED / RUNTIME EVIDENCE PENDING**  
> Evidence date: 2026-08-21  
> Working branch: `release-closure-p0`  
> Current sampled head: `29602f4d0f5117f174ae4f4c806145c420635050`  
> Draft PR: `#135 — release: close NODE-73 code-addressable P0 gates`

## 1. Current final decision

NODE-73 has a fail-closed source implementation for final product acceptance, and multiple code-addressable P0 gaps are now source-closed on `release-closure-p0`. The current LUMI release is still **not eligible for PRODUCT ACCEPTED status** because canonical dependency, Hosted CI, PostgreSQL, actual container build/attestation, Terraform, Staging, Production, live-provider, rollback and DR evidence remain incomplete.

# NOT ACCEPTED — SEE BLOCKING GAPS

`LUMI AI DESIGN OS — PRODUCT ACCEPTED` remains reserved for a future immutable V2 machine decision where every required P0/upstream gate has real PASS evidence and `blockers=[]`.

## 2. Canonical final policy and dependency blocker

Final Acceptance requires:

```text
all P0 = PASS
Critical/High cannot be deferred into green
P0 BLOCKED_EXTERNAL = NO-GO
P0 DEFERRED = NO-GO
unresolved release blockers = 0
all required upstream gates = PASS
all final approvals = APPROVED
```

The canonical dependency gate is:

```text
python3 scripts/validate_uv_workspace_lock.py
uv lock --check
uv sync --all-packages --frozen
```

The checked-in `uv.lock` remains stale relative to the 17-member root workspace. Missing lock-manifest workspace packages remain exactly:

```text
lumi-auth
lumi-domain
lumi-project-core
lumi-asset-storage
lumi-image-generation
lumi-video-generation
```

`uv.lock` must not be hand-edited. `.github/workflows/regenerate-uv-lock.yml` already implements the canonical minimum-permission resolver flow, but no resolver-generated replacement lock is claimed because the local environment cannot perform external package resolution and GitHub-hosted jobs continue to fail before executable steps begin.

## 3. Code-addressable P0 source closure

### 3.1 Platform Provider spend / durable paid side effects

NODE-20/NODE-27/Hosted Model Gateway source contracts bind Provider attempt lifecycle, canonical cost ledger/reservations, platform daily Provider spend stop and fail-closed ambiguous outcomes. Real PostgreSQL/provider evidence is still required.

### 3.2 Sandbox production egress topology

Production IaC separates the general Internet-egress branch from restricted Sandbox/outbox topology; child Sandbox execution still preserves `--network none`. Live Staging/Production network probes are still required.

### 3.3 Canonical image producer-to-Worker path

Image generation is source-bound:

```text
POST /generations
→ GenerationRuntimeGateway
→ ImageGenerationControlPlane
→ canonical Generation + Task + image_generation_spec
→ job.dispatch.requested outbox
→ MediaJobOutboxDispatcher
→ lumi.jobs.image.transform / lumi.media.image
→ Worker Media image_transform
→ HostedImageGenerationRuntime
```

The producer contract covers DB-only creation, identity/semantic-hash routing, outbox publish ordering, Worker Hosted entrypoint and API/Worker runtime provenance. PostgreSQL and real Worker execution remain pending.

### 3.4 Hosted Video provider-truth cancellation

Cancellation remains intent until Provider terminal truth is known. Source tests/contracts lock same-request reconciliation, Provider success winning cancellation races, transport-error recovery and `allow_quality_retry=False` after cancellation intent so no replacement paid request is created. Hosted/PostgreSQL/live-provider execution remains pending.

### 3.5 Private Model Gateway deployment binding

The cross-layer deployment contract requires Provider model/media secrets only on `model-gateway`, while Agent Runtime/Worker Media receive private Gateway URL + HMAC secret and use signed provider-neutral clients. Staging, Production, ECS declared-secret materialization, private clients and runtime source provenance are cross-checked. Model Gateway, Production IaC, NODE-71 Staging and Final Acceptance workflows all gate this source contract.

This is not a claim of zero Internet egress for Agent/Worker; it is a claim of Provider-secret centralization and private Hosted model path source/deployment binding. Deployed-task evidence remains pending.

### 3.6 P0-4 attested runtime-image identity and promotion — source-closed

The runtime-image source path has now been hardened beyond a static `manifest-v1.json` declaration.

#### Build recipe → digest mapping

`scripts/validate_runtime_image_build_pipeline.py` now validates each of the six runtimes independently:

```text
runtime
→ exact Dockerfile
→ context: .
→ linux/amd64
→ exact rc-${GITHUB_SHA} tag
→ own build-step digest
→ own GitHub attestation subject/digest
→ own provenance output
→ own SBOM digest reference
→ own freeze fragment
```

The contract no longer relies only on global counts such as “six build steps” or “six attest steps”. `.dockerignore` is now a Runtime Image Closure trigger and cannot silently exclude a runtime `source_paths` entry declared by the production runtime manifest.

#### Registry digest → GitHub attestation → exact source SHA

The live attestation verifier requires:

- actual registry digest resolution;
- canonical signer workflow `.github/workflows/build-runtime-image-set.yml`;
- exact `GITHUB_SHA` source digest;
- exact `refs/heads/release-closure-p0` source ref;
- exact workflow ref;
- hosted-runner identity policy;
- BuildKit provenance metadata;
- SPDX SBOM metadata.

`scripts/runtime_image_set.py` now refuses to freeze a six-runtime set unless the report-level attestation `source_digest` equals the frozen RC SHA and every runtime result carries the same signer/source policy. The frozen attestation metadata also carries the report SHA-256 and source digest.

Negative drills now reject stale source SHA, per-runtime policy drift, mutable image refs, image swaps, mixed build runs and failed/missing attestation reports.

#### NODE-71 attestation seal

`validate_staging_runtime_image_binding.py` cross-checks:

```text
NODE-71 evidence RC
↔ frozen image-set RC
↔ exact build run
↔ six image digests/provenance
↔ downloaded attestation report bytes/hash
↔ attestation source SHA
```

`bind_node71_runtime_image_decision.py` then seals the verified result into the passed NODE-71 decision as an exact `runtime_image_binding` field set containing:

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

The sealer recalculates `decision_id`, so runtime-image attestation identity is inside the decision identity. NODE-71 workflow contract locks ordering so sealing occurs before decision provenance capture/self-verification/archive.

`validate_node71_decision_artifact.py` now refuses to create or validate provenance for a passed decision that lacks this seal, has a mismatched source SHA, or differs from the provenance copy. Therefore an old-format passed NODE-71 decision cannot satisfy the current artifact contract.

#### NODE-72 Production promotion

`production-deployment-gate.py` directly requires the NODE-71 runtime-image seal and rechecks RC SHA/version, positive image-build run id, frozen artifact ref, attestation report SHA-256, attestation source SHA and exact six-runtime count. Production image digests must still equal NODE-71 accepted images exactly.

The normalized seal is included in the Production gate payload and therefore contributes to `gate_id`.

`validate_production_deployment_contract.py` now contains negative drills for missing runtime seal, source-SHA swap, invalid build run, malformed report hash, artifact-ref swap and unexpected fields. `validate_production_node71_workflow_contract.py` independently interlocks the NODE-71 sealer workflow contract with the NODE-72 promotion gate.

**Important evidence boundary:** this closes the source/anti-regression chain. It does not prove that any current RC images were actually built, pushed, attested, frozen, accepted in Staging or promoted to Production.

## 4. Hosted CI evidence — current head

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
terraform-static job_id: 96703575564 -> failure / logs_url=null / steps=null
source-contract job_id: 96703575742 -> failure / logs_url=null / steps=null
contract-gate job_id: 96703588716 -> failure / logs_url=null / steps=null
```

### Final Product Acceptance

```text
run_id: 32459558476
source-contract job_id: 96703576056 -> failure / logs_url=null / steps=null
canonical-lock-gate job_id: 96703576351 -> failure / logs_url=null / steps=null
node73-final-contract-gate job_id: 96703611450 -> failure / logs_url=null / steps=null
final-decision -> skipped
```

These jobs failed before executable steps started. There is no evidence that checkout, Python source contracts, `uv`, Ruff, Pyright, pytest, PostgreSQL, Docker, registry attestation, Terraform, Staging or Production commands executed in them.

Therefore:

```text
zero-step red != application/source-contract failure
zero-step red != PASS
```

The correct state remains Hosted execution evidence blocked.

## 5. Runtime evidence still required before PRODUCT ACCEPTED

### Canonical dependency / CI

- [ ] resolver regenerates `uv.lock` with all 17 workspace members;
- [ ] exact workspace validation, `uv lock --check`, and all-packages frozen sync pass;
- [ ] critical source contracts actually execute green with step/log evidence;
- [ ] Ruff/Pyright/pytest/security/dependency/secret gates execute green.

### PostgreSQL / durable state

- [ ] canonical migrations and ORM drift pass;
- [ ] durable Provider side-effect lifecycle passes against PostgreSQL;
- [ ] Provider spend reservation/reconciliation hard stop passes against PostgreSQL;
- [ ] image producer/repository and video recovery/public-generation integration execute against PostgreSQL.

### Real runtime-image supply chain

- [ ] canonical six-runtime build workflow executes for the exact RC SHA;
- [ ] six registry digest identities resolve;
- [ ] six GitHub artifact attestations verify against signer/source/ref/runner policy;
- [ ] actual BuildKit provenance and SPDX SBOMs are retrieved;
- [ ] exact `container-image-set.json` + `attestation-verification.json` artifact is frozen;
- [ ] NODE-71 downloads and verifies that exact artifact;
- [ ] real NODE-71 passed decision contains the sealed runtime-image binding;
- [ ] Production consumes those exact digests without rebuild;
- [ ] all packaged runtime entrypoints import/start and execute successfully.

### Private Gateway / Provider boundary

- [ ] deployed Agent Runtime/Worker Media tasks receive only private Gateway model credentials;
- [ ] deployed Model Gateway alone receives Provider model/media secrets;
- [ ] real Agent/image/video model requests traverse the signed private boundary;
- [ ] deployed runtime identity matches the accepted attested source.

### Terraform / Staging / Production

- [ ] Terraform fmt/validate/plan/apply executes from trusted runners;
- [ ] Production-like Staging infrastructure exists and parity checks PASS;
- [ ] Golden E2E/security/resilience/billing/performance/AI Staging scenarios PASS;
- [ ] Production migration, canary, ECS steady-state and read-only smoke PASS;
- [ ] alarm rollback/post-promotion rollback/restore drills execute;
- [ ] sandbox live restricted-egress behavior is proven.

### Live Provider quality

- [ ] production-routed image Provider/model has approved live NODE-23 quality/cost/latency evidence;
- [ ] production-routed video Provider/model has approved live NODE-23 quality/cost/latency evidence;
- [ ] no visual-quality acceptance is inferred from MockProvider/synthetic fixtures.

### Final upstream/operational gates

- [ ] NODE-66 Security real PASS;
- [ ] NODE-68 Recovery/DR real PASS;
- [ ] NODE-69 Performance/capacity real PASS;
- [ ] NODE-70 AI Regression real PASS;
- [ ] NODE-71 real sealed `passed=true` decision for the exact RC;
- [ ] NODE-72 real Production deploy/canary/smoke/rollback PASS;
- [ ] final Golden Journeys and browser/IME/upload/download/export/approval/billing/team scope pass;
- [ ] Product/Engineering/Security/Operations/Release Owner approvals and operational handoff are complete.

## 6. Current blocking facts

1. `uv.lock` is still stale by six workspace packages.
2. Critical Hosted jobs still fail before executable steps start.
3. PostgreSQL runtime/integration evidence is missing.
4. No actual six-runtime registry build/attestation/SBOM/provenance artifact exists for the current RC.
5. No real NODE-71 sealed `passed=true` Staging decision exists.
6. Model Gateway/Worker Docker start and full execution evidence remains missing.
7. Terraform plan/apply and live Staging/Production evidence remains missing.
8. Private Model Gateway and product image/video execution paths are source-closed but not proven on deployed tasks/images.
9. Live image/video Provider/model benchmark approval remains missing.
10. NODE-68/69/70/71/72 and final canary/rollback/DR evidence remain incomplete.
11. No real frozen V2 Final Acceptance package has produced `accepted=true`.

Any one P0 blocker is sufficient to prevent PRODUCT ACCEPTED.

## 7. Primary source evidence

```text
.github/workflows/build-runtime-image-set.yml
.github/workflows/runtime-image-closure-contract.yml
.github/workflows/staging-acceptance-gate.yml
.github/workflows/deploy-production.yml
.github/workflows/final-acceptance-gate.yml
production/runtime-images/manifest-v1.json
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
scripts/validate_private_model_gateway_deployment_contract.py
scripts/validate_image_generation_producer_contract.py
scripts/validate_video_cancellation_contract.py
reports/nodes/NODE-22/acceptance.md
reports/nodes/NODE-46/acceptance.md
reports/nodes/NODE-48/acceptance.md
docs/release-evidence/NODE-71-STAGING-ACCEPTANCE-RELEASE-EVIDENCE.md
docs/release-evidence/NODE-72-PRODUCTION-DEPLOYMENT-RELEASE-EVIDENCE.md
```

## 8. Completion rule

NODE-73 becomes COMPLETE only when a real immutable release package produces:

```text
accepted=true
passed=true
headline="LUMI AI DESIGN OS — PRODUCT ACCEPTED"
blockers=[]
```

with every P0, required upstream gate, Production requirement, approval and operational handoff condition evidenced for the same exact accepted RC.

Until then:

# NOT ACCEPTED — SEE BLOCKING GAPS
