# NODE-73 — Final Acceptance Release Closure

## Release posture

NODE-73 Final Acceptance remains **BLOCKED**. PR #135 (`release-closure-p0` → `node-73-final-acceptance-release`) must remain **Draft** and must not be merged until the live staging / production / immutable-evidence chain produces an auditable final `accepted=true` decision.

A green pull-request source workflow is code-addressable evidence only; it is not a substitute for NODE-71 sealed Staging, NODE-72 exact-digest promotion, or NODE-73 dispatch-only Final Acceptance.

## Code-addressable closure status

### Formal hosted PASS

- canonical Python workspace / lock / frozen install / PostgreSQL migration and ORM parity contracts
- Auth / Tenant integration and persistence schema contracts
- Tool Gateway P0 evidence chain, including independent offload audit joins and immutable AWS action pinning
- Sandbox Runtime full local Docker closure
- Hosted Video Generation full workflow closure
- Security response-boundary remediation with stable non-reflective HTTP errors
- Security First Pass remediation
- Model Gateway **FULL normal-workflow PASS**
  - normal workflow run `32683538121`
  - `source-contract`: PASS
  - `model-gateway`: PASS, including Ruff, Pyright, all non-PostgreSQL tests, hosted media boundaries, Deep Agents HTTP boundary, paid-guard unit tests, mock provider integration, and no-live-credential proof
  - `hosted-paid-guard-postgres`: PASS, including DB upgrade / ORM drift, durable paid invocation PostgreSQL acceptance, and migration downgrade / re-upgrade smoke

### Active App Shell closure

- Batch 1: FORMAL HOSTED PASS
- Batch 2: owner-only fail-closed remediation in progress for AI Workspace, Brand Kit, Export UI, VersionsUI, admin-console unused symbols, and approval-ui warning cleanup.
- Batch 2 has already demonstrated targeted ESLint PASS and Web typecheck PASS. The Web Vitest configuration lacked the TypeScript path aliases, which prevented most suites from collecting; the remediation now mirrors the five Web tsconfig aliases so real tests execute.
- With aliases applied, the full Web suite reached 121 PASS / 1 FAIL. The remaining failure is isolated to Infinite Canvas deterministic conflict injection and belongs to Batch 3, not Batch 2.
- Batch 3 remains isolated for Infinite Canvas React 19 ref/render synchronization and its stale-save deterministic gateway regression.

### Security Release Gate — second wave

Security First Pass is complete. Current fail-closed second-wave work is:

- Python dependency audit input: the current export contains local editable workspace packages and fails before vulnerability analysis; remediation must preserve frozen third-party dependency coverage rather than bypassing `pip-audit`.
- Trivy IaC/filesystem findings:
  - bounded PostgreSQL recovery bootstrap root (`DS-0002`) — requires exact path-scoped documented exception plus privilege-drop contract;
  - bootstrap platform provisioner broad S3 wildcard (`AWS-0345`) — must be replaced by explicit S3 provisioning actions;
  - intentional public HTTPS ALB (`AWS-0053`) — only exact resource-scoped documented exception is acceptable;
  - non-sandbox application Internet egress (`AWS-0104`) — first narrow from all protocols to HTTPS/443, then retain only an exact documented exception if Trivy still flags intentional provider/webhook egress.
- Dependency Review: the standalone legacy workflow is non-blocking (`continue-on-error`) and therefore its green status is **not release evidence**. The Security Release Gate invocation is the fail-closed source of truth and currently reports the native repository capability as unavailable. The release gate must not be weakened to match the legacy workflow.

## Immutable / live acceptance boundary

Still required before Final Acceptance may change to accepted:

- actual six-runtime RC registry build/push with SBOM/attestation and frozen runtime-image-set evidence;
- real NODE-71 sealed Staging `passed=true` bound to that exact image set;
- deployed production-like probes and private Model Gateway / canonical image-video runtime evidence;
- approved live provider/model/image/video benchmarks;
- production Terraform plan/apply;
- NODE-72 promotion of the exact Staging-approved digests without rebuild;
- production smoke, canary, rollback, DR and recovery evidence;
- frozen V2 Final Acceptance package;
- workflow-dispatch-only final decision with auditable `accepted=true`.

## Verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**
