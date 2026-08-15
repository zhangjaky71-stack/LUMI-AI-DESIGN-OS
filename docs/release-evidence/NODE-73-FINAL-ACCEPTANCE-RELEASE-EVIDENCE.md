# NODE-73 — Final Product Acceptance — Release Evidence

> Status: **SOURCE GATE IMPLEMENTED / FINAL PRODUCT NOT ACCEPTED / RUNTIME EVIDENCE PENDING**  
> Evidence date: 2026-08-15  
> Branch: `node-73-final-acceptance-release`

## 1. Current final decision

NODE-73 now has a fail-closed source implementation for final product acceptance, but the current LUMI release is **not eligible for PRODUCT ACCEPTED status**.

Current required headline:

# NOT ACCEPTED — SEE BLOCKING GAPS

The headline:

```text
LUMI AI DESIGN OS — PRODUCT ACCEPTED
```

is reserved exclusively for a future machine decision where all P0 scenarios and all required upstream gates are frozen and PASS with no unresolved release blocker.

## 2. Source final-gate controls implemented

### Canonical final matrix

`final/acceptance/manifest-v1.json` freezes **46** scenarios covering:

- six upstream release gates;
- Architecture;
- Golden Journeys A-D;
- Agent Intelligence;
- Design Intelligence / Canvas editability;
- Security;
- Reliability;
- Data / Provenance;
- Cost / Billing;
- Frontend / Browser;
- Performance / Capacity;
- Recovery;
- Observability;
- Production Operations;
- Documentation;
- Operational Handoff.

Exit policy requires:

```text
all P0 = PASS
Critical/High cannot be deferred into green
P0 BLOCKED_EXTERNAL = NO-GO
P0 DEFERRED = NO-GO
unresolved release blockers = 0
all required upstream gates = PASS
all final approvals = APPROVED
```

### Frozen final release identity

`final/acceptance/release-manifest-template.json` freezes:

```text
release_id
RC git SHA
RC version
migration head
Production deployment id/domain
Production deployment manifest path + SHA-256
six upstream decision path + SHA-256
final acceptance evidence path + SHA-256
release blockers
approvals
operational handoff ownership
```

### Upstream decision anti-fabrication contract

`final/acceptance/upstream-decision-template.json` and the final evaluator require each normalized upstream decision to contain:

```text
decision_id
passed=true
frozen evidence_refs[]
blockers
```

Every referenced evidence file is re-hashed at final decision time.

Performance, AI Regression, Staging Acceptance and Production Deployment decisions must also carry the exact final RC SHA/version/migration head.

### Final acceptance evaluator

`scripts/final-acceptance-gate.py` is dependency-free and fail-closed. It:

- constrains evidence paths to allowed repository roots;
- rejects repository path escape;
- verifies SHA-256 for upstream decisions, their evidence refs, Production deployment manifest and every PASS scenario evidence ref;
- rejects missing/extra/duplicate final scenarios;
- rejects `NOT_RUN` and any other non-final status;
- rejects every P0 status other than PASS;
- rejects FAIL;
- rejects Critical/High defer or external block;
- requires complete owner/reason/impact/target-release/workaround metadata for non-critical defer/block;
- requires all final Product/Engineering/Security/Operations/Release Owner approvals;
- requires complete operational-handoff ownership;
- recalculates a deterministic final decision id;
- is the only source allowed to emit `accepted=true`.

### Negative contract drills

`scripts/validate_final_acceptance_contract.py` creates isolated temporary fixtures under the Final Acceptance and Production Deployment report roots and proves the gate behavior for:

- clean fully-evidenced contract fixture accepts;
- P0 FAIL blocks;
- P0 BLOCKED_EXTERNAL blocks;
- complete P1 non-critical defer is permitted;
- incomplete P1 defer blocks;
- PASS without evidence blocks;
- open release blocker blocks;
- missing approval blocks;
- upstream `passed=false` blocks;
- upstream missing evidence refs blocks;
- upstream SHA substitution blocks;
- upstream RC substitution blocks;
- Production deployment RC substitution blocks;
- final acceptance evidence SHA substitution blocks.

The fixtures are explicitly contract-only and are deleted after validation. They are not production evidence.

### Evidence skeleton generator

`scripts/create-final-acceptance-evidence.py` creates all 46 scenarios as:

```text
status = NOT_RUN
```

`NOT_RUN` is deliberately invalid at final decision time. This prevents an empty or untouched template from becoming green.

### CI control plane

`.github/workflows/final-acceptance-gate.yml` provides:

- source contract validation;
- JSON/Python syntax validation;
- canonical `uv sync --frozen` dependency gate;
- manual final-decision mode that only reads frozen files under `reports/final-acceptance/`;
- immutable final-decision artifact upload;
- final contract job requiring source and canonical dependency gates.

The canonical dependency gate intentionally preserves the inherited root `uv.lock` freshness blocker rather than bypassing it.

### Direct hosted CI evidence

The first PR-triggered NODE-73 run is:

```text
workflow: Final Product Acceptance Gate
run_id: 31893111809
head_sha: eeaf4275739b19d3a583c110788d48aa55c988e2
canonical-lock-gate job: 95032233251
source-contract job: 95032233259
final-decision job: 95032233499 (skipped by design on pull_request)
contract-gate job: 95032239971
```

`source-contract`, `canonical-lock-gate`, and `contract-gate` completed with `conclusion=failure`, but each showed no executed steps and no assigned hosted runner. In particular:

```text
source-contract: runner_id=0, steps=[]
canonical-lock-gate: runner_id=0, steps=[]
```

The GitHub annotations for both critical jobs explicitly state:

```text
The job was not started because recent account payments have failed
or your spending limit needs to be increased.
```

Therefore **the NODE-73 Python source contract did not execute and `uv sync --frozen` did not execute in this run**. This is direct NODE-73 evidence of an external GitHub Billing/spending-limit runner-start blocker. It is not evidence that the Final Gate code passed, and it is not evidence that the Final Gate code or dependency lock failed at runtime.

The jobs still require an actual runner and green execution after the external condition is corrected. Re-running the same commit while the Billing condition is unchanged adds no validation value.

## 3. Evidence package implemented

The archive contract is documented in:

```text
reports/final-acceptance/README.md
```

A release directory contains at minimum:

```text
release-manifest.json
acceptance-evidence.json
final-decision.json
acceptance-matrix.md
benchmark-summary.json
security-summary.md
performance-summary.md
recovery-summary.md
cost-reconciliation.md
browser-e2e.md
known-gaps.md
upstream/*.json
```

No mutable `latest` package is permitted.

## 4. Final acceptance procedure implemented

The operator procedure is documented in:

```text
docs/acceptance/NODE-73-FINAL-ACCEPTANCE-RUNBOOK.md
```

It freezes one RC, collects six upstream gates, executes Golden Journeys A-D, completes the remaining matrix, freezes hashes, completes operational handoff and runs the final evaluator.

## 5. Runtime evidence required before PRODUCT ACCEPTED

All boxes remain intentionally unchecked.

### Upstream release gates

- [ ] NODE-66 Security has a real PASS decision with zero applicable release blocker.
- [ ] NODE-68 Recovery/DR has Production-like restore/PITR/object-recovery PASS evidence.
- [ ] NODE-69 Performance has measured launch-profile/capacity PASS evidence.
- [ ] NODE-70 AI Regression has a real baseline/candidate release PASS decision.
- [ ] NODE-71 has a Production-like Staging `passed=true` acceptance decision for the exact RC.
- [ ] NODE-72 has a real Production deployment/canary/smoke/rollback PASS decision for the exact RC.

### Golden product journeys

- [ ] Journey A Zero-to-Brand executes end-to-end on the final RC.
- [ ] Journey B precision local edit proves product/logo/QR invariants and editable structural change.
- [ ] Journey C multi-size campaign proves layout adaptation rather than naive stretching.
- [ ] Journey D failure injection proves recovery without duplicate paid generation/corrupt artifact/version loss.

### Security / reliability

- [ ] Cross-tenant leak = 0 for final release corpus.
- [ ] Sandbox escape = 0 for final release corpus.
- [ ] Secret exposure = 0 for final release corpus.
- [ ] Prompt injection cannot widen tool authority.
- [ ] SSRF metadata/private targets are denied.
- [ ] Payment/credit replay is denied.
- [ ] Queue/event/webhook/provider retry paths remain idempotent.
- [ ] Bad-deploy and service-restart recovery is exercised.

### Quality / design intelligence

- [ ] Deterministic hard-constraint critical suite is PASS.
- [ ] Precision-edit critical cases are all PASS.
- [ ] Visual/Brand/Identity quality reaches the NODE-70 frozen release threshold.
- [ ] Final Canvas artifacts remain structurally editable with Layers/Inspector/Versions.
- [ ] No critical AI regression remains.

### Cost / billing

- [ ] Provider request ↔ Generation ↔ Operation ↔ Cost Ledger ↔ AgentRun/Task ↔ Billing sample reconciliation is complete.
- [ ] No material unexplained provider spend remains.
- [ ] Org/run/video/invite limits are proven at the durable runtime enforcement point.
- [ ] Platform-wide daily provider-dollar hard stop is durably enforced and tested.

### Data / provenance

- [ ] Final artifacts expose required source/parent/model/provider/agent/recipe/skills/prompt hash/constraints/brand/quality provenance.
- [ ] Creator/time/git/runtime/rights metadata is complete.
- [ ] Archive/delete/retention/audit behavior is validated for the final release.

### Frontend / browser

- [ ] Core Projects/Workspace/Canvas/Layers/Inspector/Timeline/Brand Kit/Versions/Export/Approval flows have no P0 dead-end.
- [ ] Billing/Team surfaces match release scope without placeholder functionality.
- [ ] Chrome primary flow PASS.
- [ ] Edge primary flow PASS.
- [ ] Chinese IME/font/upload/download PASS.
- [ ] Safari core flow PASS or valid non-critical deferral with full gap metadata.

### Performance / recovery / observability

- [ ] NODE-69 launch profile is PASS for final RC.
- [ ] Autoscaling/media isolation supports the launch envelope.
- [ ] DB PITR/restore and object recovery are PASS.
- [ ] Recovery reconciliation does not blindly retry ambiguous provider operations.
- [ ] Logs/metrics/traces correlate request/Agent/Tool/Model/Worker evidence.
- [ ] SLO dashboards and alerts are live and tested.

### Production operations

- [ ] Production HTTPS/domain/data/secrets/WAF/observability/backups are live.
- [ ] Exact Staging-accepted image digests are deployed in Production.
- [ ] All intended runtime transports/entrypoints/images are production-proven.
- [ ] Migration succeeds with correct evidence.
- [ ] API canary succeeds.
- [ ] Canary alarm rollback is tested.
- [ ] ECS steady-state evidence passes.
- [ ] Production smoke passes.
- [ ] Post-promotion rollback is exercised.
- [ ] Provider quotas/billing webhook/support/admin/on-call are ready.
- [ ] Production Sandbox egress isolation is reviewed and tested.

### Documentation and handoff

- [ ] Architecture/NODE/ADR/API/Event/Design IR/Constraint/DB/Runbook/Security/Benchmark/Staging/Production docs are release-accurate.
- [ ] Operator guide and user/admin basics are release-accurate.
- [ ] Product approval = APPROVED.
- [ ] Engineering approval = APPROVED.
- [ ] Security approval = APPROVED.
- [ ] Operations approval = APPROVED.
- [ ] Release Owner approval = APPROVED.
- [ ] All eight operational handoff owners are assigned.

### Repository / CI

- [ ] NODE-73 Final Product Acceptance Gate receives a runner and source-contract executes green.
- [ ] Canonical `uv sync --frozen` executes green.
- [ ] The inherited stale root `uv.lock` blocker is resolved.
- [ ] Canonical Security/CI/Dependency/Secret gates execute green.

## 6. Current blocking facts

At source-gate implementation time:

1. NODE-68/69/70/71/72 still have unresolved Production-like/runtime/cloud evidence.
2. NODE-72 explicitly remains GO-LIVE BLOCKED and Production has not been proven deployed by its evidence.
3. NODE-71 has no real `passed=true` Production-like Staging RC decision.
4. The full six-runtime production transport/image promotion chain is not yet proven.
5. Platform-wide daily provider-dollar hard stop is not yet proven as durable runtime enforcement.
6. Production Sandbox egress isolation remains unresolved.
7. The root canonical dependency lock freshness blocker remains unresolved.
8. NODE-73 hosted run `31893111809` was blocked before runner start by the account Billing/spending-limit condition; neither the Python source contract nor the canonical dependency sync executed.
9. NODE-73 has not yet produced a real final evidence package for any Production release.

Any one of these is sufficient to prevent PRODUCT ACCEPTED status when it maps to a P0 release requirement.

## 7. Source evidence locations

```text
final/acceptance/manifest-v1.json
final/acceptance/release-manifest-template.json
final/acceptance/upstream-decision-template.json
scripts/final-acceptance-gate.py
scripts/create-final-acceptance-evidence.py
scripts/validate_final_acceptance_contract.py
.github/workflows/final-acceptance-gate.yml
reports/final-acceptance/README.md
docs/acceptance/NODE-73-FINAL-ACCEPTANCE-RUNBOOK.md
```

## 8. Completion rule

NODE-73 is COMPLETE only when a real release package produces:

```text
accepted=true
passed=true
headline="LUMI AI DESIGN OS — PRODUCT ACCEPTED"
blockers=[]
```

and every P0, required upstream gate, Production requirement and operational handoff condition is evidenced.

Until that happens, the correct project decision remains:

# NOT ACCEPTED — SEE BLOCKING GAPS
