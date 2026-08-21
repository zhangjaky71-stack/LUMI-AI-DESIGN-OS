# NODE-71 — Staging End-to-End Acceptance — Release Evidence

> Evidence date: 2026-08-21  
> Branch: `release-closure-p0`  
> Current sampled head: `a27dc1fbc70edbd663318253dded507e5093d2a3`  
> Status: **ACCEPTANCE HARNESS + STAGING IAC SOURCE IMPLEMENTED / STAGING RC NOT DEPLOYED / GO-LIVE BLOCKED**

## Decision

NODE-71 has a fail-closed, versioned Staging acceptance control plane plus production-like Staging IaC source definitions. This is **not** evidence that a Staging release candidate has been deployed or accepted. No real Staging URL, executed immutable six-runtime image set, completed environment-parity proof, Golden E2E, resilience/security drills, browser matrix, NODE-69 launch run, NODE-70 production AI release decision, or final approver set has been evidenced for the current RC.

## Current repository reality

- Canonical Staging IaC exists under `infra/iac/environments/staging/` and shares the same production-class module topology as the Production environment.
- Local Compose infrastructure remains local-only and is not accepted as Staging evidence.
- The API exposes `/health/live`, `/health/ready`, and `/version`; NODE-71 uses those endpoints only for read-only remote preflight.
- Provider model/media secrets are source-bound to `model-gateway`. Agent Runtime and Worker Media receive the private Model Gateway URL plus HMAC secret for Hosted model access.
- `scripts/validate_private_model_gateway_deployment_contract.py` now spans Staging/Production IaC secret ownership, ECS secret materialization, Agent/Worker private clients and runtime-image provenance.
- Model Gateway, Production IaC, **Staging Acceptance**, and Final Acceptance workflows all execute and syntax-gate that cross-layer contract. `scripts/validate_model_gateway_contract.py` independently locks this wiring so removing the Staging binding cannot silently pass by deleting only one validator.
- Root workspace membership and checked-in `uv.lock` still differ by six packages: `lumi-auth`, `lumi-domain`, `lumi-project-core`, `lumi-asset-storage`, `lumi-image-generation`, and `lumi-video-generation`. The lockfile remains a real frozen-install blocker and is not hand-edited.

Therefore NODE-71 does **not** report `staging RC deployed` or `staging acceptance passed` as complete.

## Implemented source baseline

- Versioned 30-scenario acceptance manifest: `staging/acceptance/manifest-v1.json`.
- 10-check environment parity contract: `staging/acceptance/environment-parity-v1.json`.
- Synthetic-only evidence template with Org A/B, platform ops and billing account matrix.
- Explicit provider-mode recording for MockProvider, provider sandbox/test mode and small production-candidate quality samples.
- Fail-closed `scripts/staging-acceptance-gate.py`.
- Machine JSON + human Markdown acceptance decisions with deterministic `decision_id`.
- P0 requires evidenced PASS; `BLOCKED_EXTERNAL` never substitutes for P0 PASS.
- PASS requires `actual`, `evidence_ref`, and `owner`.
- Open Critical/High issues block.
- All required environment parity checks must have real PASS evidence.
- Engineering, security, product and release-owner approvals must all be APPROVED.
- Production customer data is forbidden; test data and isolated Staging secrets are required.
- Read-only `scripts/staging-preflight.py` requires HTTPS, exact host ACK, Staging environment ACK, exact RC version, no redirects, health/readiness/version checks and core security headers.
- Dependency-free `scripts/validate_staging_acceptance_contract.py` provides negative drills.
- `.github/workflows/staging-acceptance-gate.yml` contains source-contract, canonical-lock, remote read-only preflight, evidence decision and artifact paths.
- The canonical dependency gate is: `validate_uv_workspace_lock.py -> uv lock --check -> uv sync --all-packages --frozen`.
- NODE-71 source-contract directly executes and syntax-gates the private Model Gateway deployment contract.
- Workflow-dispatch inputs are transferred via environment variables instead of direct shell interpolation.
- Evidence paths are constrained below `reports/staging-acceptance/`.

## Acceptance coverage

The manifest includes P0/P1 scenarios for:

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

## Direct GitHub Actions evidence — current head

Sampled head: `a27dc1fbc70edbd663318253dded507e5093d2a3`.

### Staging Acceptance Gate

```text
run_id: 32456978107
source-contract job_id: 96696044522 -> failure, logs_url=null, steps=[]
canonical-lock-gate job_id: 96696044272 -> failure, logs_url=null, steps=[]
contract-gate job_id: 96696078959 -> failure, logs_url=null, steps=[]
remote-read-only-preflight -> skipped on pull_request by design
acceptance-decision -> skipped on pull_request by design
```

The key jobs have no executed steps. Therefore checkout, Python contract execution, `validate_uv_workspace_lock.py`, `uv lock --check`, and `uv sync --all-packages --frozen` are **not evidenced as having run**.

### Corroborating release workflows on the same head

```text
Runtime Image Closure
run_id: 32456978005
runtime-image-closure job_id: 96696043625 -> failure, logs_url=null, steps=[]

Model Gateway
run_id: 32456978136
source-contract job_id: 96696044002 -> failure, logs_url=null, steps=null
hosted-paid-guard-postgres -> skipped
model-gateway -> skipped

Production IaC Contract
run_id: 32456977615
terraform-static job_id: 96696042282 -> failure, logs_url=null, steps=null
source-contract job_id: 96696042430 -> failure, logs_url=null, steps=null
contract-gate job_id: 96696068577 -> failure, logs_url=null, steps=null

Image Generation
run_id: 32456977880
image-generation-contract job_id: 96696042319 -> failure, logs_url=null, steps=null
quality / Worker image smoke / integration / benchmark -> skipped

Video Generation
run_id: 32456977960
video-generation-contract job_id: 96696042648 -> failure, logs_url=null, steps=null
quality / Worker video smoke / integration / benchmark -> skipped

Final Product Acceptance Gate
run_id: 32456977991
source-contract job_id: 96696043548 -> failure, logs_url=null, steps=null
canonical-lock-gate job_id: 96696043713 -> failure, logs_url=null, steps=null
node73-final-contract-gate job_id: 96696073915 -> failure, logs_url=null, steps=null
final-decision -> skipped
```

This is the same zero-step Hosted-runner failure pattern seen on earlier heads. These red jobs are neither application-test failures nor PASS evidence. No Ruff, Pyright, pytest, PostgreSQL, Docker, Terraform, runtime-image build, Staging probe, or application command is proven to have executed in the sampled critical jobs.

## Contract drills still required to execute

Once Hosted execution is available, `scripts/validate_staging_acceptance_contract.py` must prove:

- empty evidence cannot PASS;
- the manifest contains the intended product surface and unique IDs;
- a complete synthetic fixture can pass the evaluator logic;
- P0 `NOT_RUN` blocks;
- PASS without evidence blocks;
- internal scenarios cannot abuse `BLOCKED_EXTERNAL`;
- valid external P0 blockage still blocks go-live;
- open Critical issues block;
- environment parity failure blocks.

These remain control-plane drills only and cannot replace real Staging acceptance.

## Release blockers

- [ ] Hosted Staging `source-contract` actually executes and passes with step/log evidence.
- [ ] Canonical lock is resolver-regenerated; exact workspace validation, `uv lock --check`, and `uv sync --all-packages --frozen` execute and pass.
- [ ] Production-like Staging infrastructure is actually planned/applied and reachable.
- [ ] Exact immutable six-runtime RC image set is built, attested, promoted and deployed.
- [ ] SBOM/provenance attestations are verified against the exact RC SHA and image digests.
- [ ] All 10 environment parity checks have real evidence.
- [ ] Synthetic Org A/B/ops/billing accounts are provisioned without production customer data.
- [ ] Read-only remote preflight passes on the exact RC.
- [ ] Golden Brand Project E2E passes.
- [ ] Precision Edit E2E passes product/Logo/QR/version invariants.
- [ ] Image/video canonical producer -> Worker -> Provider -> Artifact paths execute in Staging.
- [ ] Private Model Gateway secret/path boundary is proven on deployed tasks, not only source configuration.
- [ ] Resilience and security scenarios execute; Critical/High failures are zero.
- [ ] Billing/cost reconciliation executes and passes.
- [ ] NODE-69 Profile G Staging evidence exists for the exact RC.
- [ ] NODE-70 production-candidate release evidence exists for the exact RC/model configuration.
- [ ] Chrome/Edge, Chinese IME/font/upload/download P0 checks pass; Safari P1 is honestly evidenced or externally blocked.
- [ ] Data lifecycle, backup restore and observability correlation evidence pass.
- [ ] Engineering/security/product/release-owner approvals are complete.
- [ ] Final `decision.json` returns `passed=true` for the exact immutable RC.

## Current status

```text
ACCEPTANCE MANIFEST: IMPLEMENTED SOURCE
ENVIRONMENT PARITY CONTRACT: IMPLEMENTED SOURCE
STAGING IAC: IMPLEMENTED SOURCE / NOT APPLIED
PRIVATE MODEL GATEWAY STAGING BINDING: SOURCE-CLOSED / DEPLOYED PROOF PENDING
EVIDENCE SCHEMA/TEMPLATE: IMPLEMENTED SOURCE
FAIL-CLOSED RC EVALUATOR: IMPLEMENTED SOURCE
READ-ONLY REMOTE PREFLIGHT: IMPLEMENTED SOURCE / NOT RUN AGAINST RC
NEGATIVE CONTRACT DRILLS: IMPLEMENTED SOURCE / HOSTED EXECUTION BLOCKED
CANONICAL LOCK: STALE / RESOLVER EXECUTION BLOCKED
STAGING ACCEPTANCE WORKFLOW: IMPLEMENTED SOURCE
HOSTED CI EXECUTION: BLOCKED BEFORE STEPS START
REAL STAGING RC: MISSING
REAL RUNTIME-IMAGE ATTESTATION: MISSING
REAL GOLDEN E2E / SECURITY / RESILIENCE / PERF / AI EVIDENCE: MISSING
FINAL APPROVALS: MISSING
NODE-71 GO-LIVE STATUS: BLOCKED
```

NODE-72 may supply the deployment machinery, but Production promotion must not consume NODE-71 until the exact immutable RC has a real acceptance decision with `passed=true`.