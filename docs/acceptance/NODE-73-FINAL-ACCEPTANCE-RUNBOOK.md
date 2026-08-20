# NODE-73 — Final Product Acceptance Runbook

> Status: **SOURCE RUNBOOK / FINAL PRODUCT NOT YET ACCEPTED**

## 1. Purpose

This runbook is the final Go/No-Go procedure for LUMI AI Design OS. It does not replace NODE-66～72; it freezes and re-validates their real evidence together with the product journeys, documentation, repository governance and operational handoff.

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

For the image-generation path specifically, the accepted Worker Media image provenance must include the executable Celery/task runtime, Worker Media Docker build recipe and production CLI entrypoint, NODE-46 domain package, private Model Gateway adapter, versioned generation codec, canonical Postgres repository, reference/cost/outbox/storage ports, canonical artifact adapter, Hosted composition root and bounded S3 implementation. A worker-media digest without those source bindings is not acceptable evidence.

## 14. Freeze acceptance evidence

After all scenario statuses are final, compute the SHA-256 of `acceptance-evidence.json` and put the exact path/hash into `release-manifest.json`.

Do not edit evidence after this point. Any edit requires re-freezing the release manifest and re-running the gate.

## 15. Freeze upstream, Production and repository-governance evidence

The final release manifest must also freeze:

```text
six upstream decision wrappers
production deployment manifest
repository-governance report
```

Each file is validated again by SHA-256 at decision time.

The repository-governance report must prove both NODE-73 release refs satisfy `LUMI_RELEASE_PROTECTION_PROFILE_V1` and that protected `release-closure-p0` still points to the exact final RC SHA. The manual Final Product Acceptance workflow re-queries GitHub live before evaluating the product decision.

## 16. Complete operational handoff and GitHub-backed release authorization

Assign and record:

- on-call owner;
- support owner;
- incident commander rotation;
- first-day watch owner;
- quality/cost review owner;
- security/dependency review owner;
- DR drill owner;
- capacity review owner.

Required approval roles remain:

```text
Product
Engineering
Security
Operations
Release Owner
```

However, manually typing five `APPROVED` strings is **not** valid release evidence.

### 16.1 Configure the approval identity policy

Copy `final/acceptance/release-approval-policy-template.json` into the release evidence area and replace every `PENDING` role principal with real GitHub login allowlists.

The canonical policy requires:

```text
repository = zhangjaky71-stack/LUMI-AI-DESIGN-OS
PR = #135
base = node-73-final-acceptance-release
head = release-closure-p0
minimum distinct human approvers >= 3
Engineering approver != Security approver
Security approver != Release Owner approver
bots forbidden
review commit == exact final RC SHA
```

Do not invent role principals. If the organization has not assigned a real person/login to a role, authorization remains blocked.

### 16.2 Freeze the authorization request

Create `reports/final-acceptance/<release-id>/authorization-request.json` from `final/acceptance/release-authorization-request-template.json` and freeze the configured approval policy by `path + sha256`.

The request also freezes the complete operational handoff and exact RC identity.

### 16.3 Obtain real GitHub approvals

The role principals must submit actual GitHub **APPROVED** reviews on PR #135 after the final RC SHA is selected.

Only the latest decisive review from each actor counts. A review is rejected when it is:

- by the PR author;
- by a bot;
- not `APPROVED`;
- attached to an older commit;
- superseded by a later decisive `CHANGES_REQUESTED` or dismissed review;
- outside the role's configured login allowlist.

### 16.4 Capture provenance-backed authorization

Run:

```bash
python3 scripts/capture_release_authorization.py \
  --request reports/final-acceptance/<release-id>/authorization-request.json \
  --output reports/final-acceptance/<release-id>/release-authorization.json
```

The resulting `LUMI_RELEASE_AUTHORIZATION_V1` records, per role:

```text
actor GitHub login
review id
review URL
exact RC commit id
submitted_at
```

It also freezes the request and policy by SHA-256 and proves the minimum distinct-actor and separation-of-duties rules.

The canonical assembler and final package validator re-validate this structure. Only after successful provenance validation do they emit the simple five-role `APPROVED` status map consumed by `final-acceptance-gate.py`.

### 16.5 Live approval re-verification

The manual Final Product Acceptance workflow gives only `final-decision` the read-only `pull-requests: read` permission. A short-lived `GITHUB_TOKEN` is exposed only to the live-authorization step, which verifies that:

- PR #135 is still open on the expected base/head refs;
- PR head still equals the frozen RC SHA;
- every frozen review still exists;
- every review actor still matches;
- every review is still `APPROVED` for the exact RC;
- each frozen approval is still that actor's latest decisive review.

The live result is archived as `release-authorization-live.json` before the product acceptance decision runs.

At the current checkpoint, PR #135 has **zero submitted reviews** and the role-principal policy template is intentionally `PENDING`. Therefore Final Approval Provenance is currently **BLOCKED_EXTERNAL**, not PASS.

## 17. Run the final gate

The recommended release path is the manual `Final Product Acceptance Gate` workflow, because it performs both live repository-governance and live GitHub-review re-verification before the product decision.

The underlying deterministic product gate remains:

```bash
python3 scripts/final-acceptance-gate.py \
  --release reports/final-acceptance/<release-id>/release-manifest.json \
  --evidence reports/final-acceptance/<release-id>/acceptance-evidence.json \
  --output reports/final-acceptance/<release-id>/final-decision.json
```

Do not treat a standalone invocation of this last command as full release authorization; the canonical package and live governance/approval checks must already have passed.

## 18. Decision handling

If the gate exits non-zero or reports blockers:

```text
NOT ACCEPTED — SEE BLOCKING GAPS
```

Keep the release out of final acceptance. Fix or explicitly re-scope the actual blocker; do not edit the matrix, fabricate approvals or delete a scenario to make the report green.

Only when the machine decision returns `accepted=true` after the full release workflow may the release headline be:

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

The code-addressable image-generation and release-trust path is now materially stronger than the earlier source baseline:

- `image.transform` no longer returns an accepted-only placeholder; it enters the canonical TaskJobStore and Hosted NODE-46 runtime;
- Worker Media and Model Gateway have concrete production image/source closure and private provider boundaries;
- six-runtime release Actions are pinned to immutable commit SHAs and use scoped workflow permissions;
- RC image attestations are verified against the canonical signer workflow, exact source SHA/ref, GitHub-hosted runner identity, BuildKit SLSA provenance and SPDX SBOM;
- `attestation-verification.json` is SHA-256-bound into the frozen runtime-image set and re-validated by NODE-71;
- canonical `uv.lock` regeneration is bound to one dispatch SHA and fails if the release branch moves;
- Final Acceptance requires a frozen strong repository-governance report and re-verifies GitHub protection live;
- Final Acceptance now requires provenance-backed GitHub PR approvals rather than unauthenticated `APPROVED` strings.

These are source/contract closures, not deployment or human-approval proof. Final acceptance remains blocked by at least:

- canonical `uv.lock` regeneration and successful `uv sync --all-packages --frozen`;
- successful trusted PostgreSQL migration/ORM-drift/NODE-20/NODE-27/NODE-46 integration execution;
- successful Worker Media and Model Gateway production-image build/start proof in a trusted runnable environment;
- real six-runtime image build/start/promotion and live attestation evidence;
- Production-like Staging, Production smoke/canary/rollback and DR evidence;
- remaining NODE-68～72 runtime/cloud evidence requirements;
- strong protection/ruleset configuration for both NODE-73 release refs (currently GitHub reports `protected=false`);
- a usable Administration-read `RELEASE_GOVERNANCE_TOKEN` for live detailed protection verification;
- configured real GitHub role principals for Product/Engineering/Security/Operations/Release Owner;
- at least three distinct human exact-RC APPROVED reviews satisfying the role/SoD policy (currently PR #135 has zero submitted reviews).

Latest sampled GitHub-hosted release-critical jobs continue to exhibit the established pre-execution failure mode: failed jobs have `steps=null` and `logs_url=null`, so no checkout, Python, `uv`, Docker, pytest, PostgreSQL, Terraform or application command is evidenced as having run. Those red jobs therefore provide neither code-failure diagnostics nor PASS evidence.

Therefore this runbook's current final outcome remains intentionally:

# NOT ACCEPTED — SEE BLOCKING GAPS
