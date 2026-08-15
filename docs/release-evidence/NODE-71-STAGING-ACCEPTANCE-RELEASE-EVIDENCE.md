# NODE-71 — Staging End-to-End Acceptance — Release Evidence

> Evidence date: 2026-08-15  
> Branch: `node-71-staging-acceptance-release`  
> Status: **ACCEPTANCE HARNESS IMPLEMENTED / STAGING RC NOT DEPLOYED / GO-LIVE BLOCKED**

## Decision

NODE-71 now has a fail-closed, versioned acceptance-control baseline. This is not a claim that a production-like Staging release candidate exists or has passed. No real Staging URL, immutable RC image set, synthetic account matrix, Golden E2E, resilience/security drills, browser matrix, NODE-69 launch run, NODE-70 production AI release decision, or final approver set has been evidenced in this environment.

## Repository reality discovered

- Local Compose infrastructure exists for PostgreSQL/pgvector, Redis, RabbitMQ, MinIO, Mailpit and later observability/recovery overlays.
- Local Compose documentation explicitly classifies those credentials/management ports as local-only and not suitable for Staging/Production exposure.
- `infra/terraform` currently contains only `.gitkeep`; the repository does not yet provide deployed production-like Staging IaC.
- The API exposes `/health/live`, `/health/ready`, and `/version`, which NODE-71 reuses for read-only remote preflight.

Therefore NODE-71 does **not** report `staging RC deployed` as complete. Environment provisioning/deployment remains part of NODE-72, while NODE-71 defines exactly what that environment must prove before go-live.

## Implemented source baseline

- Versioned 30-scenario acceptance manifest: `staging/acceptance/manifest-v1.json`.
- 10-check environment parity contract: `staging/acceptance/environment-parity-v1.json`.
- Synthetic-only evidence template with Org A/B, platform ops and billing account matrix.
- Explicit provider-mode recording for MockProvider, provider sandbox/test mode and small production-candidate quality sample.
- Fail-closed `scripts/staging-acceptance-gate.py`.
- Machine JSON + human Markdown acceptance decisions with deterministic `decision_id`.
- P0 requires evidenced PASS; `BLOCKED_EXTERNAL` never substitutes for P0 PASS.
- PASS requires `actual`, `evidence_ref`, and `owner`.
- `BLOCKED_EXTERNAL` is valid only where the manifest declares an external dependency and still blocks P0 go-live.
- Open Critical/High issues block.
- All required environment parity checks must be evidenced PASS.
- Engineering, security, product and release-owner approvals must all be APPROVED.
- Production customer data is forbidden; test data and isolated Staging secrets are required.
- Read-only `scripts/staging-preflight.py` requiring HTTPS, exact host ACK, Staging environment ACK, exact RC version, no redirects, health/readiness/version checks and core security headers.
- Dependency-free `scripts/validate_staging_acceptance_contract.py` with negative drills.
- Staging Acceptance Gate workflow with source contract, frozen lock gate, manual remote preflight, manual evidence decision and artifact output.
- workflow-dispatch values are passed through environment variables rather than interpolated into shell source.
- Detailed execution plan and evidence archive contract under `docs/staging/` and `reports/staging-acceptance/`.

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

## Contract drills

Once CI can execute, `scripts/validate_staging_acceptance_contract.py` must prove:

- the empty evidence template cannot PASS;
- the manifest contains at least the full intended product surface and unique IDs;
- a complete synthetic contract fixture can theoretically PASS the evaluator;
- P0 `NOT_RUN` blocks;
- PASS without `evidence_ref` blocks;
- internal scenarios cannot abuse `BLOCKED_EXTERNAL`;
- valid external P0 blockage still blocks go-live;
- open Critical issue blocks;
- environment parity failure blocks.

These are control-plane drills only. They do not satisfy real Staging acceptance.

## Release blockers

- [ ] Staging Acceptance Gate `source-contract` actually executes on a GitHub runner.
- [ ] Frozen `canonical-lock-gate` executes and passes.
- [ ] GitHub Billing/spending-limit condition is resolved so hosted jobs can start.
- [ ] Root `uv.lock` freshness blocker inherited from NODE-66 is resolved.
- [ ] Production-like Staging environment exists.
- [ ] Exact immutable RC SHA/image digests/migration head are deployed.
- [ ] All 10 environment parity checks have real evidence.
- [ ] Synthetic Org A/B/ops/billing accounts are provisioned without production customer data.
- [ ] Read-only remote preflight passes on the exact RC.
- [ ] Golden Brand Project E2E passes.
- [ ] Precision Edit E2E passes all product/Logo/QR/version invariants.
- [ ] Resilience scenarios execute and pass.
- [ ] Security scenarios execute with zero Critical/High failure.
- [ ] Billing/cost reconciliation executes and passes.
- [ ] NODE-69 Profile G staging evidence exists for the exact RC.
- [ ] NODE-70 production-candidate release evidence exists for the exact RC/model configuration.
- [ ] Chrome and Edge P0 browser flows pass.
- [ ] Chinese IME/font/upload/download P0 checks pass.
- [ ] Safari P1 is either evidenced PASS or honestly recorded as `BLOCKED_EXTERNAL`.
- [ ] Data lifecycle and backup restore checks pass.
- [ ] Observability correlation evidence exists.
- [ ] No open Critical/High issues remain.
- [ ] Engineering/security/product/release-owner approvals are complete.
- [ ] Final `decision.json` says `passed=true` for the exact RC SHA.

## Current status

```text
ACCEPTANCE MANIFEST: IMPLEMENTED
ENVIRONMENT PARITY CONTRACT: IMPLEMENTED
EVIDENCE SCHEMA/TEMPLATE: IMPLEMENTED
FAIL-CLOSED RC EVALUATOR: IMPLEMENTED
READ-ONLY REMOTE PREFLIGHT: IMPLEMENTED
NEGATIVE CONTRACT DRILLS: IMPLEMENTED
STAGING ACCEPTANCE WORKFLOW: IMPLEMENTED
REAL STAGING ENVIRONMENT: MISSING
REAL RC DEPLOYMENT: MISSING
REAL GOLDEN E2E EVIDENCE: MISSING
REAL SECURITY/RESILIENCE/PERF/AI EVIDENCE: MISSING
FINAL APPROVALS: MISSING
NODE-71 GO-LIVE STATUS: BLOCKED
```

NODE-72 may implement the deployment/IaC required to create the production-like environment, but Production deployment may not consume NODE-71 until an acceptance decision for the exact immutable RC returns `passed=true`.
