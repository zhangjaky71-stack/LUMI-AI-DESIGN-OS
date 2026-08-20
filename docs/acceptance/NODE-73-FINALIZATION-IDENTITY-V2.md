# NODE-73 Finalization Identity V2 — Source RC vs Evidence Head

Status: **MANDATORY MIGRATION BASELINE**

This document corrects a structural identity problem discovered during NODE-73 Release Closure. It does not introduce NODE-74 and it does not change the Final Acceptance verdict.

## 1. Why V1 is cyclic

A Git commit cannot reliably contain evidence that is itself required to prove approval of that same commit.

The invalid cycle is:

```text
freeze RC SHA
  -> humans approve RC SHA
  -> generate approval report
  -> commit approval report
  -> branch SHA changes
  -> prior human approvals are now attached to the old SHA
```

The same problem exists if a live branch-protection report that contains the final branch head SHA must itself be committed into that same branch head.

Therefore these identities MUST NOT be collapsed into one SHA.

## 2. Two independent immutable identities

### 2.1 Source RC SHA

`source_rc_sha` is the product/source commit that was actually used for:

- six runtime image builds;
- runtime provenance and attestations;
- database migration identity;
- Staging acceptance;
- Production deployment;
- product/runtime evidence.

This is the existing `release_candidate.git_sha` semantic.

It is immutable after runtime promotion begins.

### 2.2 Evidence Head SHA

`evidence_head_sha` is the final Git commit on `release-closure-p0` that contains:

- final acceptance matrix inputs;
- production/upstream frozen evidence references;
- repository-governance policy;
- approval identity policy;
- authorization request;
- final package;
- canonical Final Decision source code/workflow/contracts.

It is the exact GitHub Actions `GITHUB_SHA` used to execute Final Decision and the exact PR #135 head commit reviewed by human approvers.

`evidence_head_sha` MAY differ from `source_rc_sha` and normally will be a descendant of it.

## 3. Required relationship

Final Decision MUST prove:

```text
repository == zhangjaky71-stack/LUMI-AI-DESIGN-OS
GITHUB_REF == refs/heads/release-closure-p0
GITHUB_SHA == evidence_head_sha
PR #135 head SHA == evidence_head_sha
live protected release-closure-p0 head == evidence_head_sha
source_rc_sha is an ancestor of evidence_head_sha
```

The final artifact must bind both SHA values separately.

## 4. What MAY be committed before Evidence Head freeze

The final evidence commit MAY contain only information that exists before final human approval/live governance observation, including:

- Source RC identity;
- immutable image/runtime evidence;
- production/staging/upstream evidence;
- complete scenario evidence;
- `LUMI_RELEASE_GOVERNANCE_POLICY_V1` policy;
- `LUMI_RELEASE_APPROVAL_POLICY_V1` role/principal policy;
- authorization request and operational handoff;
- final package with approval statuses still `PENDING`;
- canonical Final Decision implementation and contracts.

## 5. What MUST NOT be committed after Evidence Head freeze

After `evidence_head_sha` is selected, the following MUST NOT be committed back into `release-closure-p0`:

- live branch-protection capture tied to `evidence_head_sha`;
- GitHub PR review authorization result tied to `evidence_head_sha`;
- `final-decision.json`;
- any other artifact whose validity depends on the exact final Evidence Head SHA.

Those are runtime decision artifacts and must be uploaded as GitHub Actions artifacts.

Any source commit after human reviews invalidates the reviews and requires a new Evidence Head plus fresh approvals.

## 6. Correct finalization sequence

```text
1. Freeze Source RC SHA.
2. Build/promote/accept exact Source RC through NODE-71/NODE-72/Production evidence.
3. Assemble all non-live final evidence and policies.
4. Commit the final package with approvals PENDING.
5. Select this commit as Evidence Head SHA.
6. Require Source RC SHA to be an ancestor of Evidence Head SHA.
7. Enable strong protection/ruleset controls for both NODE-73 release refs.
8. Configure real GitHub principal allowlists for the five approval roles.
9. Human reviewers submit APPROVED reviews on PR #135 at exact Evidence Head SHA.
10. Dispatch Final Product Acceptance Gate from exact Evidence Head SHA.
11. Final Decision live-queries branch protection and PR reviews.
12. Final Decision derives APPROVED statuses in memory only.
13. Inner 46-scenario product gate evaluates the enriched in-memory release state.
14. Outer final-decision.json binds Source RC SHA, Evidence Head SHA, live governance/report hashes, live human authorization/report hashes, canonical package/evidence hashes and workflow run identity.
15. Upload final-decision.json and live reports as Actions artifacts. Do not commit them back to the release branch.
```

## 7. Governance evidence semantics

The release package must freeze a **governance policy**, not a live head-bound governance report.

Canonical pre-final policy:

`final/acceptance/repository-governance-policy-template.json`

The policy states which branches/profile must be enforced. Final Decision captures the actual GitHub state live and requires the observed evidence-head branch head to equal `GITHUB_SHA`.

## 8. Human authorization semantics

The release package must freeze:

- configured five-role GitHub principal policy;
- authorization request;
- operational handoff;
- Source RC identity.

It must NOT require a pre-committed approval report.

At Final Decision time the approval collector uses `evidence_head_sha` as the required GitHub review commit while retaining Source RC identity from the request.

The resulting authorization report is runtime evidence only.

## 9. Product-gate compatibility

The stable inner `final-acceptance-gate.py` may continue to require five `APPROVED` statuses.

The canonical outer Final Decision wrapper must derive those statuses from the live GitHub authorization report and inject them into an in-memory copy of the release manifest.

The committed release manifest itself must remain `PENDING` for human approval statuses before Final Decision.

A direct standalone invocation of the inner product gate is not a canonical release authorization path.

## 10. Final decision artifact schema expectations

The canonical outer decision must contain at least:

```text
release_candidate.git_sha = Source RC SHA
execution_identity.git_sha = Evidence Head SHA
execution_identity.workflow_ref
execution_identity.run_id/run_url
source_rc_ancestor_of_evidence_head = true
canonical input hashes
live repository governance report path + sha256
live authorization report path + sha256
product_decision_id
outer decision_id over all of the above
```

## 11. Current migration status

The repository already has most V2 primitives:

- strong live governance collector;
- approval principal policy/request templates;
- live GitHub PR review collector;
- canonical Final Decision wrapper;
- outer final artifact live-control binding.

However earlier Release Closure code still contains V1 assumptions in the package/assembler/governance/authorization path, including head-bound precommitted evidence semantics. Those assumptions must be migrated before NODE-73 can be considered internally consistent.

Until that migration is complete:

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**
