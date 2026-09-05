# NODE-73 — Final Product Acceptance Runbook

> Status: **SOURCE RUNBOOK / FINAL PRODUCT NOT YET ACCEPTED**

## 1. Purpose

This runbook is the final Go/No-Go procedure for LUMI AI Design OS. It does not replace NODE-66～72; it freezes and re-validates their real evidence together with the product journeys, documentation, repository governance and operational handoff.

The default outcome is:

```text
NOT ACCEPTED — SEE BLOCKING GAPS
```

The gate may emit `LUMI AI DESIGN OS — PRODUCT ACCEPTED` only when every P0 and every required upstream gate is evidenced PASS and no release blocker remains.

## 2. Freeze one exact Source RC

Before final acceptance, identify exactly one **Source RC**:

```text
release_candidate.git_sha
version
migration_head
production deployment_id
production domain
```

`release_candidate.git_sha` is the product/source commit actually used for six-runtime images, migrations, Staging and Production. It is **not** the later Final Evidence Head SHA.

Do not mix evidence from different Source RC commits, migration heads or image sets.

The exact Production deployment manifest must already exist under:

```text
reports/production-deployments/<deployment-id>/manifest.json
```

and must match the Source RC.

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

Every identity-bearing upstream decision must use the exact Source RC identity.

STOP if any required upstream gate is not `passed=true`.

## 4. Create the final evidence skeleton

Run:

```bash
python3 scripts/create-final-acceptance-evidence.py \
  --release-id <release-id> \
  --git-sha <source-rc-sha> \
  --version <version> \
  --migration-head <migration-head> \
  --output reports/final-acceptance/<release-id>/acceptance-evidence.json
```

The generator creates all 46 scenarios as `NOT_RUN`. Do not replace unexecuted work with `PASS` just to complete the matrix.

## 5. Execute Golden Journey A — Zero-to-Brand

Use a production-scope test account and the frozen Source RC.

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

The final package must contain real Source-RC-bound evidence for:

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

## 14. Prepare V2 pre-final policies and request

NODE-73 Finalization Identity V2 deliberately separates:

```text
Source RC SHA      = product/runtime identity
Evidence Head SHA  = final evidence/workflow/review identity
```

A Git commit cannot contain a live approval/protection report whose validity depends on that same commit SHA. Therefore **do not commit live governance or approval results into the package**.

### 14.1 Governance policy

Use the canonical policy:

```text
final/acceptance/repository-governance-policy-template.json
```

It declares the required two release refs and `LUMI_RELEASE_PROTECTION_PROFILE_V1`. It does not contain a live branch head.

### 14.2 Approval principal policy V2

Copy:

```text
final/acceptance/release-approval-policy-v2-template.json
```

into the release evidence area and replace every `PENDING` principal with real GitHub login allowlists.

The policy requires:

```text
PR = #135
base = node-73-final-acceptance-release
head = release-closure-p0
minimum distinct human approvers >= 3
Engineering approver != Security approver
Security approver != Release Owner approver
PR author excluded
bots forbidden
review commit == exact Evidence Head SHA
latest decisive review semantics
```

Do not invent principals. Missing real people/logins means Final Approval remains blocked.

### 14.3 Authorization request V2

Create a request from:

```text
final/acceptance/release-authorization-request-v2-template.json
```

The request freezes:

```text
release_id
Source RC SHA/version/migration_head
configured approval policy path + sha256
operational handoff
PR #135 identity
```

The request intentionally contains **no Evidence Head SHA and no APPROVED result**.

## 15. Assemble the committed V2 package

Use `scripts/final-acceptance-assembler-v2.py` with the exact Production manifest, six upstream decisions, scenario results, governance policy and V2 authorization request.

Canonical output:

```text
reports/final-acceptance/<release-id>/release-manifest-v2.json
reports/final-acceptance/<release-id>/acceptance-evidence.json
```

Then run:

```bash
python3 scripts/validate_final_acceptance_package_v2.py \
  --release reports/final-acceptance/<release-id>/release-manifest-v2.json
```

The committed package MUST have:

```text
approvals.product = PENDING
approvals.engineering = PENDING
approvals.security = PENDING
approvals.operations = PENDING
approvals.release_owner = PENDING
```

It MUST NOT contain `release_authorization` or live `repository_governance` reports. A pre-approved committed package is invalid.

## 16. Freeze the Evidence Head

Commit all non-live final evidence, configured policies, authorization request, V2 package and canonical V2 decision source/workflow/contracts to `release-closure-p0`.

The resulting commit becomes:

```text
evidence_head_sha
```

Final Decision requires:

```text
Source RC SHA is an ancestor of Evidence Head SHA
GITHUB_SHA == Evidence Head SHA
PR #135 head == Evidence Head SHA
protected release-closure-p0 head == Evidence Head SHA
GITHUB_REF == refs/heads/release-closure-p0
canonical workflow ref == final-acceptance-gate.yml@refs/heads/release-closure-p0
```

After the Evidence Head is selected, **do not commit any live authorization, live governance or final-decision artifact back to `release-closure-p0`**. Any new source commit creates a new Evidence Head and invalidates prior reviews.

## 17. Enable governance, collect reviews and run Final Decision

### 17.1 Strong branch protection

Both:

```text
node-73-final-acceptance-release
release-closure-p0
```

must satisfy `LUMI_RELEASE_PROTECTION_PROFILE_V1`, including strict required checks, PR review requirement, stale review dismissal, last-push approval, admin enforcement, linear history, conversation resolution, no approval bypass, no force pushes and no branch deletion.

Final Decision requires a read-only `RELEASE_GOVERNANCE_TOKEN` capable of reading detailed repository Administration protection state.

### 17.2 Human reviews on the Evidence Head

The configured role principals submit real GitHub **APPROVED** reviews on PR #135 after the Evidence Head is final.

A review is rejected when it is:

- by the PR author;
- by a bot;
- not `APPROVED`;
- attached to any commit other than Evidence Head;
- superseded by a later decisive `CHANGES_REQUESTED` or dismissed review;
- outside the role's configured login allowlist;
- unable to satisfy minimum distinct actors or separation of duties.

The authorization result is generated live as `LUMI_RELEASE_AUTHORIZATION_V2`. It records Source RC and Evidence Head separately.

### 17.3 Dispatch the canonical workflow

Dispatch `Final Product Acceptance Gate` from exact `release-closure-p0` Evidence Head with:

```text
release_manifest_path = reports/final-acceptance/<release-id>/release-manifest-v2.json
acceptance_evidence_path = reports/final-acceptance/<release-id>/acceptance-evidence.json
```

The `final-decision` job checks out exact `github.sha` with `fetch-depth: 0` and runs only:

```text
validate_final_acceptance_package_v2.py
final-acceptance-decision-v2.py
```

The outer decision performs, in this order:

```text
validate committed V2 package
capture live strong repository governance
capture live Evidence-Head GitHub approvals
prove Source RC ancestor of Evidence Head
project five APPROVED statuses into an in-memory release object
run stable 46-scenario final-acceptance-gate.py
bind all canonical input hashes and live-report hashes into final-decision-v2.json
```

Runtime-only outputs include:

```text
runtime-v2/repository-governance-live.json
runtime-v2/release-authorization-live.json
final-decision-v2.json
```

They are GitHub Actions artifacts only. Do not commit them back to the Evidence Head branch.

## 18. Decision handling

If any V2 source/package/live-control/product gate exits non-zero or reports blockers:

```text
NOT ACCEPTED — SEE BLOCKING GAPS
```

Keep the release out of final acceptance. Do not edit the matrix, fabricate approvals, weaken protection, or delete evidence to make the report green.

Only when the V2 outer machine decision returns `accepted=true` may the release headline be:

```text
LUMI AI DESIGN OS — PRODUCT ACCEPTED
```

A direct standalone invocation of the inner `final-acceptance-gate.py` is **not** canonical release authorization.

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

The code-addressable release-trust path now includes:

- durable Provider side-effect/cost controls and private Model Gateway boundaries;
- real Worker Media image-generation execution path;
- exact six-runtime Source-RC image identity, SBOM and provenance contracts;
- NODE-71 build-artifact binding and NODE-72 decision provenance binding;
- immutable release Action pins and scoped permissions;
- Finalization Identity V2 with separate Source RC and Evidence Head identities;
- V2 governance policy rather than a self-referential committed live report;
- V2 GitHub approval policy/request where reviews bind Evidence Head, not Source RC;
- committed V2 package with approvals forced to `PENDING`;
- canonical V2 Final Decision that derives approvals only from live GitHub state and binds both SHA identities plus live report hashes into the final artifact;
- executable V2 assembler/package negative-drill contract.

These are source/contract closures, not runtime or human-approval proof. Final acceptance remains blocked by at least:

- canonical `uv.lock` regeneration and successful `uv sync --all-packages --frozen`;
- successful trusted PostgreSQL migration/ORM-drift/NODE-20/NODE-27/NODE-46 integration execution;
- successful Worker Media and Model Gateway production-image build/start proof;
- real six-runtime image build/start/promotion and live attestation evidence;
- Production-like Staging, Production smoke/canary/rollback and DR evidence;
- remaining NODE-68～72 runtime/cloud evidence requirements;
- strong protection/ruleset configuration for both NODE-73 release refs (currently GitHub reports `protected=false`);
- a usable Administration-read `RELEASE_GOVERNANCE_TOKEN`;
- configured real GitHub role principals for Product/Engineering/Security/Operations/Release Owner;
- at least three distinct human Evidence-Head APPROVED reviews satisfying role/SoD policy (currently PR #135 has zero submitted reviews);
- successful Hosted CI execution; sampled release-critical jobs have continued to fail before executable steps with `steps=null` and `logs_url=null`.

No zero-step red job is treated as a product failure or PASS.

Therefore this runbook's current final outcome remains intentionally:

# NOT ACCEPTED — SEE BLOCKING GAPS
