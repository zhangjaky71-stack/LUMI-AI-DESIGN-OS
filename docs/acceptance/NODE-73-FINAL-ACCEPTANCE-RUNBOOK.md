# NODE-73 — Final Product Acceptance Runbook

> Status: **SOURCE RUNBOOK / FINAL PRODUCT NOT YET ACCEPTED**

## 1. Purpose

This runbook is the final Go/No-Go procedure for LUMI AI Design OS. It does not replace NODE-66～72; it freezes and re-validates their real evidence together with the product journeys, documentation and operational handoff.

The default outcome is:

```text
NOT ACCEPTED — SEE BLOCKING GAPS
```

The gate may emit `LUMI AI DESIGN OS — PRODUCT ACCEPTED` only when every P0 and every required upstream gate is evidenced PASS and no release blocker remains.

## 2. Freeze one exact release candidate

Before final acceptance, identify exactly one RC:

```text
git_sha
version
migration_head
production deployment_id
production domain
```

Do not mix evidence from different commits, migration heads or image sets.

The exact Production deployment manifest must already exist under:

```text
reports/production-deployments/<deployment-id>/manifest.json
```

and must match the final RC.

## 3. Collect six upstream machine decisions

Normalize the following into `reports/final-acceptance/<release-id>/upstream/` using `final/acceptance/upstream-decision-template.json`:

```text
security
recovery
performance
ai-regression
staging-acceptance
production-deployment
```

Each wrapper must freeze the real evidence behind the decision and include:

```text
decision_id
passed=true
evidence_refs[] with path + sha256
blockers=[]
```

Performance, AI Regression, Staging Acceptance and Production Deployment must also use the exact final RC identity.

STOP if any upstream gate is not `passed=true`.

## 4. Create the final evidence skeleton

Run:

```bash
python3 scripts/create-final-acceptance-evidence.py \
  --release-id <release-id> \
  --git-sha <git-sha> \
  --version <version> \
  --migration-head <migration-head> \
  --output reports/final-acceptance/<release-id>/acceptance-evidence.json
```

The generator creates all 46 scenarios as `NOT_RUN`. Do not replace unexecuted work with `PASS` just to complete the matrix.

## 5. Execute Golden Journey A — Zero-to-Brand

Use a production-scope test account and the frozen RC.

Natural-language brief:

> 为一家精品咖啡品牌做完整设计，包括研究、品牌定位、视觉方向、Logo、品牌规范、包装、菜单、海报、社媒和短视频。

Collect evidence for:

```text
Create Project
Brief Agent
research with sources
brand strategy
creative directions
human approval
moodboard
Brand Kit
image/design generation
editable Canvas artifacts
Critic / Brand / Identity QA
repair
versions/provenance
multi-format export
Agent Timeline
cost ledger
pause/resume
```

A rendered image alone is not PASS. The final assets must remain structurally editable and versioned.

## 6. Execute Golden Journey B — Precision Local Edit

Use an existing approved poster/version and issue:

> 产品和Logo都不要动，二维码位置大小不变；背景改成黑色，标题缩小15%。

Prove with before/after data and visual evidence:

```text
exact selected version
product identity unchanged
logo unchanged
QR payload unchanged
QR geometry/position invariant
QR remains scannable
title structural size change approximately -15%
background local/structural edit
new immutable version created
old version remains restorable
quality/constraint result PASS
```

Any silent product/logo/QR mutation is a P0 failure.

## 7. Execute Golden Journey C — Multi-size Campaign

From one approved design generate/adapt:

```text
1:1
4:5
9:16
16:9
```

Prove layout adaptation rather than naive stretching, and show preserved Brand/Product constraints with independent DesignVersions where layout changes materially.

## 8. Execute Golden Journey D — Failure Recovery

During a controlled run inject:

```text
Agent worker restart
provider timeout/429/5xx
duplicate request/event
SSE disconnect/reconnect
```

Required result:

```text
run resumes or ends explicitly
no duplicate paid generation
no corrupt artifact
no approved version loss
ambiguous provider operation is reconciled, not blindly retried
```

## 9. Execute the remaining matrix

Use `final/acceptance/manifest-v1.json` as the canonical list. Cover:

- Architecture and governed deviations;
- Agent/tool/model authority and idempotency;
- Design/Canvas/constraint quality;
- Security release corpus;
- Reliability and rollback;
- Artifact provenance and data lifecycle;
- Cost/Billing reconciliation and hard controls;
- Frontend/browser/IME flows;
- Launch performance/capacity;
- recovery/PITR/object restore;
- observability/SLO alerts;
- production operations;
- documentation;
- operational handoff.

Every PASS must reference frozen evidence files by path + SHA-256.

## 10. Gap policy

Only a genuinely non-critical P1/P2 item may use:

```text
DEFERRED_NON_CRITICAL
BLOCKED_EXTERNAL
```

and it must record:

```text
owner
reason
impact
target_release
workaround
```

P0 and Critical/High items cannot be deferred into a green release.

## 11. Cost reconciliation

For a statistically useful sample of real accepted runs, reconcile:

```text
Provider request
Generation
Idempotency Operation
Cost Ledger
AgentRun / Task
Billing usage / credit entry
```

Any estimated value must state confidence/reconciliation status. Unexplained material spend blocks `COST-01`.

The platform-wide daily provider-dollar hard stop must be proven at a durable runtime boundary; a value written only in a release manifest is not enforcement.

## 12. Security acceptance

STOP immediately on any release-blocking condition, including:

```text
cross-tenant leak
sandbox escape
secret exposure
unauthorized prompt-injection tool escalation
SSRF to metadata/private targets
payment/credit replay
unresolved Critical/High without an approved release policy exception
```

Do not continue final sign-off while a STOP-SHIP issue is open.

## 13. Production acceptance

The final package must contain real evidence for:

```text
HTTPS/domain
production DB/storage/broker/secrets
backup/recovery
WAF/rate limit
observability/SLO
exact immutable image digests
migration success
API canary
alarm rollback
ECS steady state
production smoke
post-promotion rollback
provider quotas
billing webhook
support/admin/on-call
```

Source Terraform is not Production evidence.

## 14. Freeze acceptance evidence

After all scenario statuses are final, compute the SHA-256 of `acceptance-evidence.json` and put the exact path/hash into `release-manifest.json`.

Do not edit evidence after this point. Any edit requires re-freezing the release manifest and re-running the gate.

## 15. Freeze upstream and Production evidence

The final release manifest must also freeze:

```text
six upstream decision wrappers
production deployment manifest
```

Each file is validated again by SHA-256 at decision time.

## 16. Complete operational handoff

Assign and record:

- on-call owner;
- support owner;
- incident commander rotation;
- first-day watch owner;
- quality/cost review owner;
- security/dependency review owner;
- DR drill owner;
- capacity review owner.

Required approvals:

```text
Product
Engineering
Security
Operations
Release Owner
```

All must be `APPROVED`.

## 17. Run the final gate

```bash
python3 scripts/final-acceptance-gate.py \
  --release reports/final-acceptance/<release-id>/release-manifest.json \
  --evidence reports/final-acceptance/<release-id>/acceptance-evidence.json \
  --output reports/final-acceptance/<release-id>/final-decision.json
```

Or run the manual `Final Product Acceptance Gate` workflow against the two frozen files.

## 18. Decision handling

If the gate exits non-zero or reports blockers:

```text
NOT ACCEPTED — SEE BLOCKING GAPS
```

Keep the release out of final acceptance. Fix or explicitly re-scope the actual blocker; do not edit the matrix or delete a scenario to make the report green.

Only when the machine decision returns `accepted=true` may the release headline be:

```text
LUMI AI DESIGN OS — PRODUCT ACCEPTED
```

## 19. Post-acceptance operating cadence

After a real accepted production release, continue:

```text
weekly provider / cost / quality review
monthly security / dependency review
quarterly DR drill
AI release gate for every production AI change
capacity planning and autoscaling review
customer feedback -> governed data flywheel
```

Final acceptance is the start of governed operations, not permission to stop validation.

## 20. Current project state

As of this source baseline, NODE-68～72 still contain unresolved runtime/cloud evidence requirements and GitHub hosted CI has been blocked before runner start by an account Billing/spending-limit condition on the latest readiness nodes.

Therefore this runbook's current final outcome is intentionally:

# NOT ACCEPTED — SEE BLOCKING GAPS
