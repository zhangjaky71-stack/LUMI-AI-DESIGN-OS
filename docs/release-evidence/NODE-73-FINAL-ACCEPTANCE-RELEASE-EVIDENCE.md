# NODE-73 — Final Product Acceptance — Release Evidence

> Status: **SOURCE CLOSURE ADVANCED / FINAL PRODUCT NOT ACCEPTED / RUNTIME EVIDENCE PENDING**  
> Evidence date: 2026-08-21  
> Working branch: `release-closure-p0`  
> Draft PR: `#135 — release: close NODE-73 code-addressable P0 gates`

## 1. Current final decision

NODE-73 has a fail-closed source implementation for final product acceptance, and multiple code-addressable P0 gaps have been closed on `release-closure-p0`. The current LUMI release is still **not eligible for PRODUCT ACCEPTED status** because canonical dependency, Hosted CI, PostgreSQL, container, Terraform, Staging, Production, live-provider, rollback and DR evidence remain incomplete.

Current required headline:

# NOT ACCEPTED — SEE BLOCKING GAPS

The headline:

```text
LUMI AI DESIGN OS — PRODUCT ACCEPTED
```

is reserved exclusively for a future machine decision where every P0 requirement and required upstream gate is frozen and PASS with no unresolved release blocker.

## 2. Final source-gate controls

### Canonical final matrix and decision policy

`final/acceptance/manifest-v1.json` freezes the final release scenarios spanning upstream gates, architecture, Golden Journeys, Agent/Design Intelligence, security, reliability, provenance, cost/billing, browser, performance, recovery, observability, Production operations, documentation and handoff.

Exit policy remains fail-closed:

```text
all P0 = PASS
Critical/High cannot be deferred into green
P0 BLOCKED_EXTERNAL = NO-GO
P0 DEFERRED = NO-GO
unresolved release blockers = 0
all required upstream gates = PASS
all final approvals = APPROVED
```

`scripts/final-acceptance-gate.py` remains the only source allowed to emit `accepted=true`. Frozen V2 release/evidence identity, anti-fabrication hashes, release approvals and operational handoff remain mandatory.

### Canonical dependency gate

Final Acceptance now explicitly requires:

```text
python3 scripts/validate_uv_workspace_lock.py
uv lock --check
uv sync --all-packages --frozen
```

The checked-in `uv.lock` is currently stale. The exact root-workspace members missing from the current lock manifest are:

```text
lumi-auth
lumi-domain
lumi-project-core
lumi-asset-storage
lumi-image-generation
lumi-video-generation
```

This is a system-wide frozen-install blocker. `uv.lock` must **not** be hand-edited.

The canonical resolver workflow already exists as `.github/workflows/regenerate-uv-lock.yml` and is intentionally two-stage/minimum-permission:

```text
resolver job (contents: read)
  -> uv lock
  -> exact workspace-member validation
  -> uv lock --check
  -> uv sync --all-packages --frozen
  -> compile
  -> upload uv.lock + digest only

write job (contents: write)
  -> verify artifact digest
  -> verify branch head has not moved
  -> require changed files == uv.lock only
  -> commit/push uv.lock only
```

No resolver-generated lock is claimed yet because the current available local execution environment has no external package-resolution/DNS access and GitHub-hosted jobs are still failing before executable steps begin.

## 3. Code-addressable P0 closure completed on release-closure-p0

### 3.1 Platform-wide Provider spend / durable paid side effects

Source-level NODE-20/NODE-27 release closure includes platform Provider spend hard-stop contracts, durable provider-attempt lifecycle barriers, fail-closed ambiguous outcomes and Hosted Model Gateway paid invocation binding. Runtime PostgreSQL/cloud evidence is still required before release acceptance.

### 3.2 Sandbox egress source topology

The IaC source contract separates the app identity SG, explicit Internet-egress SG and restricted Sandbox/outbox SG branch. Sandbox source topology prohibits public egress and permits required internal/S3 transport. Live Production-like egress probes remain required; source topology is not Production proof.

### 3.3 Canonical image producer-to-Worker closure

The image-generation path is now statically bound end-to-end:

```text
POST /generations
  -> GenerationRuntimeGateway
  -> ImageGenerationControlPlane
  -> canonical Generation + Task
  -> versioned image_generation_spec in Task.input_json
  -> canonical job.dispatch.requested outbox row
  -> MediaJobOutboxDispatcher
  -> lumi.jobs.image.transform / lumi.media.image
  -> Worker Media image_transform
  -> HostedImageGenerationRuntime
```

`scripts/validate_image_generation_producer_contract.py` now checks:

- production API binding and idempotency;
- canonical Generation/Task/spec/outbox creation ordering;
- DB-only producer boundary with no direct Provider/Celery side effect;
- organization/project/task/operation/semantic-hash dispatch identity;
- canonical outbox dispatcher queue/routing and publish ordering;
- Worker `image.transform` Hosted runtime entrypoint;
- API/Worker runtime-image provenance;
- self-gating in Image Generation and Final Acceptance workflows.

Image Generation workflow now executes this producer contract in its first contract job. PostgreSQL execution and real Worker image execution are still pending.

### 3.4 Hosted Video provider-truth cancellation closure

Video cancellation now treats `tasks.cancellation_requested_at` as intent, not proof that an accepted async Provider request stopped.

Source regressions and static gates lock:

- Provider `CANCELLED` is the only Provider result that self-certifies cancellation;
- `PENDING`, `SUCCEEDED`, `FAILED`, missing recovery state and cancel transport exceptions remain unresolved/provider-truth driven;
- a Provider success racing with cancellation is preserved and completed;
- a cancel API transport timeout preserves the original provider recovery row and reconciles the same `provider_request_id`;
- cancellation reconciliation polls the same request at most once per Worker invocation;
- `resume(..., allow_quality_retry=False)` prevents a replacement paid request after cancellation intent;
- estimate/submit must remain zero on the provider-terminal recovery path.

NODE-48 remains IMPLEMENTED / VALIDATING / not COMPLETE until Hosted, PostgreSQL, container and live-provider evidence execute.

### 3.5 Private Model Gateway deployment binding closure

A new cross-layer source contract now binds deployment configuration to Hosted runtime clients:

```text
scripts/validate_private_model_gateway_deployment_contract.py
```

It requires:

1. Staging and Production expose the Model Gateway through private service-discovery URL `model-gateway.<env>.lumi.internal:8080`;
2. only the `model-gateway` service receives `providers/model` and `providers/media` secrets;
3. Agent Runtime and Worker Media receive `LUMI_MODEL_GATEWAY_URL` plus `LUMI_MODEL_GATEWAY_AUTH_SECRET`, not Provider model/media credentials;
4. ECS execution IAM authorizes only each service's declared `secret_arns` and ECS task definitions inject only those declarations;
5. Hosted Agent Runtime constructs `HttpProfileModelProvider.from_env()`;
6. Hosted image generation constructs `HostedImageModelGatewayAdapter.from_env()`;
7. Hosted video generation constructs `HostedVideoGateway.from_env()`;
8. the Hosted Model Gateway service requires model/media Provider secrets and verifies signed callers restricted to `agent-runtime` / `worker-media`;
9. Agent, Worker and Model Gateway runtime-image provenance contains the private-boundary implementation sources;
10. Model Gateway, Production IaC and Final Acceptance workflows all execute and syntax-gate this contract.

This source closure intentionally does **not** claim Agent Runtime or Worker Media have no Internet egress. The current canonical Production IaC contract explicitly grants the general Internet-egress SG to services outside the restricted `sandbox-runtime` / `outbox-dispatcher` branch. The audited claim is narrower: Provider credentials remain centralized in Model Gateway and Hosted model execution is source/deployment-bound to the signed private Gateway client.

Runtime proof that the deployed task definitions and exact promoted images actually implement this boundary is still required.

### 3.6 Runtime-image source provenance

The source manifest now includes executable API, Agent Runtime, Model Gateway, Tool Gateway, Worker Media and Sandbox Runtime build/entrypoint/source provenance requirements, including the Hosted image/video and private Model Gateway implementation chains. Actual promoted-image build/start/SBOM/provenance evidence remains pending.

## 4. Hosted CI evidence — current blocker

The current GitHub-hosted runner/account condition continues to fail jobs before executable steps begin. Red zero-step jobs are **not application-test failures and are not PASS evidence**.

### Image producer closure sample

Head sampled: `ee5ca15d2849d50c70c946de0f5aac9bca252f07`

```text
Image Generation run: 32455525781
image-generation-contract job: 96691955849
conclusion: failure
steps: null
logs_url: null
quality: skipped
worker-media-image-smoke: skipped
integration: skipped
benchmark: skipped
```

### Private Model Gateway / release closure sample

Head sampled: `b45c857ee9d25276bc9d826c3e18580391d78145`

```text
Model Gateway run: 32456048585
source-contract job: 96693429449
conclusion: failure
steps: null
logs_url: null
model-gateway: skipped
hosted-paid-guard-postgres: skipped
```

```text
Production IaC run: 32456048507
source-contract job: 96693429271 -> failure / steps=null / logs_url=null
terraform-static job: 96693429489 -> failure / steps=null / logs_url=null
contract-gate job: 96693458867 -> failure / steps=null / logs_url=null
```

```text
Final Product Acceptance run: 32456048271
source-contract job: 96693428258 -> failure / steps=null / logs_url=null
canonical-lock-gate job: 96693428476 -> failure / steps=null / logs_url=null
node73-final-contract-gate job: 96693468762 -> failure / steps=null / logs_url=null
final-decision: skipped
```

No checkout, Python, new source contract, `uv`, Ruff, Pyright, pytest, PostgreSQL, Docker, Terraform or application command is evidenced as having executed in those critical jobs.

Therefore:

```text
zero-step red != application failure
zero-step red != PASS
```

The correct state remains **BLOCKED_EXTERNAL for Hosted execution evidence**.

## 5. Runtime evidence required before PRODUCT ACCEPTED

All items below remain release blockers until evidenced on the exact frozen RC.

### Canonical repository / CI

- [ ] canonical resolver regenerates `uv.lock` and exact workspace-member validation passes;
- [ ] `uv lock --check` passes;
- [ ] `uv sync --all-packages --frozen` passes;
- [ ] Model Gateway/Image/Video/Final source contracts actually execute green;
- [ ] Ruff/Pyright/pytest gates execute green;
- [ ] canonical Security/Dependency/Secret/CI gates execute green.

### PostgreSQL / durable state

- [ ] canonical Alembic migration and ORM-drift gates pass;
- [ ] NODE-20 durable side-effect provider-attempt lifecycle passes against PostgreSQL;
- [ ] NODE-27 platform Provider-cost hard stop/reconciliation passes against PostgreSQL;
- [ ] NODE-46 image producer/repository integration passes;
- [ ] NODE-48 video control-plane/recovery/privilege/public-generation integration passes;
- [ ] no historical parallel runtime tables are present where the canonical contracts require their absence.

### Runtime images / service execution

- [ ] all six runtime images build from the frozen workspace;
- [ ] packaged production entrypoints import/start successfully;
- [ ] Model Gateway readiness proves durable paid/cost dependencies;
- [ ] Worker Media image/video execution is proven in the accepted image;
- [ ] SBOM/provenance/runtime source attestations are captured for the exact promoted digests;
- [ ] Staging runs the exact accepted images and Production deploys those exact digests.

### Private Gateway / provider boundary

- [ ] deployed Agent Runtime task receives the intended private Model Gateway URL/auth secret and no Provider model/media credential;
- [ ] deployed Worker Media task receives the intended private Model Gateway URL/auth secret and no Provider model/media credential;
- [ ] deployed Model Gateway task alone receives Provider model/media secrets;
- [ ] Agent Runtime and Worker Media execute real model/media requests through the signed private Gateway boundary;
- [ ] exact runtime identities/source attestations are captured.

### Terraform / network / cloud

- [ ] Terraform fmt/validate/plan succeeds from trusted execution;
- [ ] Production-like Staging apply succeeds;
- [ ] Sandbox restricted-egress behavior is probed live;
- [ ] Production apply/deployment evidence is captured;
- [ ] WAF, secrets, backups, observability and service discovery are live and reviewed.

### Live model/provider quality

- [ ] selected production image provider/model revision has approved NODE-23 quality/cost/latency evidence;
- [ ] selected production video provider/model revision has approved NODE-23 quality/cost/latency evidence;
- [ ] no live visual-quality score is inferred from MockProvider/synthetic tests.

### Upstream release gates and final product journeys

- [ ] NODE-66 Security real PASS;
- [ ] NODE-68 Recovery/DR real PASS;
- [ ] NODE-69 Performance/capacity real PASS;
- [ ] NODE-70 AI Regression real PASS;
- [ ] NODE-71 Production-like Staging real `passed=true` for the exact RC;
- [ ] NODE-72 Production deployment/canary/smoke/rollback real PASS for the exact RC;
- [ ] Golden Journeys A-D execute on the final RC;
- [ ] browser/IME/upload/download/export/approval/billing/team release-scope journeys pass;
- [ ] final Product/Engineering/Security/Operations/Release Owner approvals are all APPROVED;
- [ ] operational-handoff owners are assigned.

## 6. Current blocking facts

1. `uv.lock` remains stale by six root-workspace packages and has not been resolver-regenerated.
2. GitHub-hosted critical jobs still fail before executable steps begin, so none of the newly strengthened source gates has Hosted PASS evidence.
3. PostgreSQL migration/integration evidence remains pending.
4. real Model Gateway and Worker Media Docker build/start/readiness/execution evidence remains pending.
5. Terraform validate/plan/apply and live Staging/Production network evidence remain pending.
6. six-runtime promoted-image identity/SBOM/provenance evidence remains pending.
7. the private Model Gateway deployment boundary is source-closed but not yet proven on deployed task definitions/images.
8. canonical image/video product producer paths are source-closed but not yet proven through full deployed end-to-end execution.
9. selected live image/video Provider/model quality evidence remains pending.
10. NODE-68/69/70/71/72 and final Production smoke/canary/rollback/DR evidence remain incomplete.
11. no real final V2 acceptance evidence package has produced `accepted=true`.

Any one P0 blocker is sufficient to prevent PRODUCT ACCEPTED status.

## 7. Source evidence locations

```text
final/acceptance/manifest-v1.json
.github/workflows/final-acceptance-gate.yml
.github/workflows/regenerate-uv-lock.yml
.github/workflows/model-gateway.yml
.github/workflows/image-generation.yml
.github/workflows/video-generation.yml
.github/workflows/production-iac-contract.yml
scripts/validate_uv_workspace_lock.py
scripts/validate_uv_lock_regeneration_contract.py
scripts/validate_image_generation_producer_contract.py
scripts/validate_video_generation_producer_binding.py
scripts/validate_video_worker_hosted_binding.py
scripts/validate_video_cancellation_contract.py
scripts/validate_private_model_gateway_deployment_contract.py
scripts/validate_production_iac_contract.py
production/runtime-images/manifest-v1.json
reports/nodes/NODE-22/acceptance.md
reports/nodes/NODE-46/acceptance.md
reports/nodes/NODE-48/acceptance.md
reports/final-acceptance/README.md
docs/acceptance/NODE-73-FINAL-ACCEPTANCE-RUNBOOK.md
```

## 8. Completion rule

NODE-73 is COMPLETE only when a real frozen release package produces:

```text
accepted=true
passed=true
headline="LUMI AI DESIGN OS — PRODUCT ACCEPTED"
blockers=[]
```

and every P0, required upstream gate, Production requirement, approval and operational handoff condition is evidenced for the exact accepted RC.

Until that happens, the correct project decision remains:

# NOT ACCEPTED — SEE BLOCKING GAPS
