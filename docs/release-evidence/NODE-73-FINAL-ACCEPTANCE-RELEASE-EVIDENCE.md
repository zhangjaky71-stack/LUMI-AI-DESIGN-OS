# NODE-73 — Final Product Acceptance — Release Evidence

> Status: **SOURCE CLOSURE ADVANCED / IMMUTABLE-GIT ATTESTED RC PROMOTION SOURCE-CLOSED / FINAL PRODUCT NOT ACCEPTED / RUNTIME EVIDENCE PENDING**  
> Evidence date: 2026-08-21  
> Working branch: `release-closure-p0`  
> Runtime provenance hardening baseline: `9388984516602c3102d985797b51ad188b910bd9`  
> Latest sampled execution head: `9388984516602c3102d985797b51ad188b910bd9`  
> Draft PR: `#135 — release: close NODE-73 code-addressable P0 gates`

## 1. Current final decision

NODE-73 has a fail-closed source implementation for final product acceptance, and multiple code-addressable P0 gaps are source-closed on `release-closure-p0`. The current LUMI release is still **not eligible for PRODUCT ACCEPTED status** because canonical dependency, Hosted CI, PostgreSQL, actual container build/attestation, Terraform, Staging, Production, live-provider, rollback and DR evidence remain incomplete.

# NOT ACCEPTED — SEE BLOCKING GAPS

`LUMI AI DESIGN OS — PRODUCT ACCEPTED` remains reserved for a future immutable V2 machine decision where every required P0/upstream gate has real PASS evidence and `blockers=[]`.

## 2. Canonical final policy and dependency blocker

Final Acceptance requires all P0 = PASS, no Critical/High deferral into green, no P0 `BLOCKED_EXTERNAL`/`DEFERRED`, zero unresolved release blockers, all required upstream gates PASS and all final approvals APPROVED.

The canonical dependency gate remains:

```text
python3 scripts/validate_uv_workspace_lock.py
uv lock --check
uv sync --all-packages --frozen
```

The checked-in `uv.lock` remains stale relative to the 17-package root workspace graph. Missing lock-manifest workspace packages remain exactly:

```text
lumi-auth
lumi-domain
lumi-project-core
lumi-asset-storage
lumi-image-generation
lumi-video-generation
```

`uv.lock` must not be hand-edited. `.github/workflows/regenerate-uv-lock.yml` already implements the minimum-permission resolver flow, but no resolver-generated replacement lock is claimed because the available local environment cannot perform external package resolution and GitHub-hosted jobs continue to fail before executable steps begin.

## 3. Code-addressable P0 source closure

### 3.1 Platform Provider spend / durable paid side effects

NODE-20/NODE-27/Hosted Model Gateway source contracts bind Provider attempt lifecycle, canonical cost ledger/reservations, platform daily Provider spend stop and fail-closed ambiguous outcomes. Real PostgreSQL/provider evidence is still required.

### 3.2 Sandbox production egress topology

Production IaC separates the general Internet-egress branch from restricted Sandbox/outbox topology; child Sandbox execution preserves `--network none`. Live Staging/Production network probes are still required.

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

### 3.6 P0-4 immutable-Git attested runtime-image identity and promotion — source-closed

The runtime-image supply chain is now hardened beyond both the static `manifest-v1.json` declaration and the earlier local-Path build recipe.

#### Exact immutable build source → digest mapping

The canonical chain is:

```text
exact release-closure-p0 Git SHA
→ context: https://github.com/${GITHUB_REPOSITORY}.git#${GITHUB_SHA}
→ exact service Dockerfile
→ linux/amd64
→ provenance: mode=max,version=v0.2
→ immutable rc-${GITHUB_SHA} image digest
→ service-specific GitHub attestation subject/digest
→ SPDX SBOM
→ frozen service fragment
```

`scripts/validate_runtime_image_build_pipeline.py` validates all six runtimes independently and rejects release-image regression to `context: .`, `{{defaultContext}}`, wrong Dockerfile, wrong platform, missing scoped Git auth, unpinned provenance version, cross-wired build digest, attestation, SBOM or freeze fragment.

`.dockerignore` remains a Runtime Image Closure trigger and declared `source_paths` cannot be silently excluded by positive ignore rules.

#### Actual BuildKit provenance → exact repository / RC SHA / Dockerfile

The previous verifier only required a non-empty provenance object with a `buildType`, builder and a `materials` array; even `materials=[]` passed its clean self-test. That did not prove the image bytes came from the exact immutable Git source intended by the release workflow.

`scripts/verify_runtime_image_attestations.py` now requires, for each actual image digest:

```text
buildType == https://mobyproject.org/buildkit@v1
invocation.configSource.uri == https://github.com/<owner>/<repo>.git#<RC_SHA>
invocation.configSource.digest.sha1 == <RC_SHA>
invocation.configSource.entryPoint == <service Dockerfile>
invocation.environment.platform == linux/amd64
materials is a non-empty array
```

It still independently requires:

- live registry digest resolution;
- canonical signer workflow `.github/workflows/build-runtime-image-set.yml`;
- exact `GITHUB_SHA` source digest;
- exact `refs/heads/release-closure-p0` source ref;
- exact workflow ref;
- hosted-runner identity policy;
- SPDX SBOM metadata.

Negative self-tests now reject wrong repository URI, stale source SHA, wrong Dockerfile entry point, wrong platform, empty materials, wrong build type and malformed provenance.

This closes the code-addressable gap between “the workflow intended to build SHA X” and “the BuildKit provenance attached to digest Y proves the exact Git source/Dockerfile/platform used to build it.”

#### Frozen image set / NODE-71 seal / NODE-72 promotion

`scripts/runtime_image_set.py` refuses to freeze the six-runtime set unless report `source_digest == frozen RC git_sha` and every runtime result carries the same signer/source policy. `validate_staging_runtime_image_binding.py` cross-checks NODE-71 evidence RC, frozen RC, exact build run, six image/provenance records, attestation report bytes/hash and source SHA.

`bind_node71_runtime_image_decision.py` seals the verified result into the passed NODE-71 decision, recalculates `decision_id`, and `validate_node71_decision_artifact.py` refuses provenance creation/verification for an unsealed or source-SHA-mismatched passed decision.

`production-deployment-gate.py` revalidates the NODE-71 runtime seal, report hash/source SHA/build-run identity and exact six-runtime count before Production promotion. Production image digests must equal NODE-71 accepted images exactly, without rebuild.

**Important evidence boundary:** this closes the source/anti-regression chain. It does not prove that any current RC images were actually built, pushed, attested, frozen, accepted in Staging or promoted to Production.

## 4. Hosted CI evidence — current sampled hardening head

Sampled head: `9388984516602c3102d985797b51ad188b910bd9`.

### Runtime Image Closure Contract

```text
run_id: 32462283655
runtime-image-closure job_id: 96711482008
conclusion: failure
logs_url: null
steps: null
```

### Staging Acceptance Gate

```text
run_id: 32462283704
canonical-lock-gate job_id: 96711482611 -> failure / logs_url=null / steps=null
source-contract job_id: 96711482808 -> failure / logs_url=null / steps=null
contract-gate job_id: 96711514824 -> failure / logs_url=null / steps=null
remote-read-only-preflight -> skipped
acceptance-decision -> skipped
```

### Production IaC Contract

```text
run_id: 32462283621
terraform-static job_id: 96711482728 -> failure / logs_url=null / steps=null
source-contract job_id: 96711483040 -> failure / logs_url=null / steps=null
contract-gate job_id: 96711522020 -> failure / logs_url=null / steps=null
```

### Final Product Acceptance Gate

```text
run_id: 32462283662
source-contract job_id: 96711482533 -> failure / logs_url=null / steps=null
canonical-lock-gate job_id: 96711482731 -> failure / logs_url=null / steps=null
node73-final-contract-gate job_id: 96711498190 -> failure / logs_url=null / steps=null
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

- [ ] resolver regenerates `uv.lock` with all 17 workspace packages;
- [ ] exact workspace validation, `uv lock --check`, and all-packages frozen sync pass;
- [ ] critical source contracts actually execute green with step/log evidence;
- [ ] Ruff/Pyright/pytest/security/dependency/secret gates execute green.

### PostgreSQL / durable state

- [ ] canonical migrations and ORM drift pass;
- [ ] durable Provider side-effect lifecycle passes against PostgreSQL;
- [ ] Provider spend reservation/reconciliation hard stop passes against PostgreSQL;
- [ ] image producer/repository and video recovery/public-generation integration execute against PostgreSQL.

### Real runtime-image supply chain

- [ ] canonical six-runtime build workflow executes for the exact RC SHA using the immutable Git context;
- [ ] six registry digest identities resolve;
- [ ] six GitHub artifact attestations verify against signer/source/ref/runner policy;
- [ ] each BuildKit provenance proves exact repository, RC SHA, service Dockerfile, `linux/amd64` and non-empty materials;
- [ ] actual SPDX SBOMs are retrieved;
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