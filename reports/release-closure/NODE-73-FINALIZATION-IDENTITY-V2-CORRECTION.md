# NODE-73 Finalization Identity V2 Correction

Status: **IDENTIFIED -> DESIGN_BASELINED -> MIGRATION_REQUIRED**

Scope: NODE-73 Release Closure only. This correction does not introduce NODE-74 and does not change the Final Acceptance verdict.

## Critical finding

The earlier release-integrity model accidentally conflated two independent Git identities:

1. the product/source release candidate SHA used to build and deploy runtimes; and
2. the final evidence/package commit from which the release decision workflow executes and which human reviewers approve.

Making both identities equal creates an impossible self-reference when approval or governance results are committed after reviewers approve the allegedly final SHA.

Example invalid cycle:

```text
select SHA A
human reviews approve A
generate release-authorization.json for A
commit release-authorization.json -> SHA B
A approvals no longer approve current head B
```

A live branch-protection report tied to the branch head has the same self-reference if the report itself must be committed into that head.

## Superseding model

The mandatory V2 model defines:

### Source RC SHA

The immutable source/product commit represented by `release_candidate.git_sha` and used for:

- runtime image build/source provenance;
- NODE-71/NODE-72 release identity;
- Staging/Production deployment;
- migration/runtime/product evidence.

### Evidence Head SHA

The final `release-closure-p0` commit containing all non-live release evidence, policy/configuration, final package and canonical Final Decision implementation.

Human reviewers approve this SHA. Final Decision executes from this SHA. Live protected branch head must equal this SHA.

Source RC and Evidence Head may differ. Source RC must be an ancestor of Evidence Head.

## New V2 primitives

Added:

- `docs/acceptance/NODE-73-FINALIZATION-IDENTITY-V2.md`
- `final/acceptance/repository-governance-policy-template.json`
- `scripts/validate_release_governance_policy.py`
- `scripts/validate_finalization_identity_v2.py`

The identity validator explicitly treats distinct Source RC and Evidence Head SHAs as valid and requires:

- execution SHA == Evidence Head;
- PR #135 head == Evidence Head;
- live protected `release-closure-p0` head == Evidence Head;
- canonical workflow/ref/repository identity;
- Source RC is a Git ancestor of Evidence Head.

Seven negative drills block execution/PR/live-head/repository/ref/workflow/ancestry mismatches.

## Required package migration

The existing Final Acceptance package/assembler path must be migrated so it freezes only information available before final live approval:

- Source RC identity;
- canonical runtime/production/upstream evidence;
- scenario evidence;
- governance **policy**, not a head-bound live governance capture;
- human approval principal policy;
- authorization request and operational handoff;
- approval statuses remain `PENDING` in the committed package.

The committed package MUST NOT require a human approval report that can only exist after the package's Evidence Head is known.

## Required Final Decision migration

After Evidence Head is frozen and no more source commits are allowed:

1. strong repository protections are enabled;
2. real human reviewers approve PR #135 at exact Evidence Head;
3. Final Decision is dispatched from exact Evidence Head;
4. live branch governance is captured and requires protected branch head == Evidence Head;
5. live PR reviews are captured and require review commit == Evidence Head;
6. approval statuses are derived in memory only;
7. the inner 46-scenario gate evaluates the enriched in-memory release state;
8. the outer decision binds both Source RC and Evidence Head plus all live report hashes;
9. live reports and final decision are Actions artifacts only and are never committed back to the release branch.

## Superseded assumptions

Any earlier NODE-73 comment/document/source rule that requires:

```text
release-closure-p0.head_sha == release_candidate.git_sha
human review commit == release_candidate.git_sha
Final Decision GITHUB_SHA == release_candidate.git_sha
```

is superseded by this V2 correction.

The correct comparisons are:

```text
release-closure-p0 live head == Evidence Head SHA
PR #135 review commit == Evidence Head SHA
Final Decision GITHUB_SHA == Evidence Head SHA
Source RC SHA is an ancestor of Evidence Head SHA
```

## Current external state

No acceptance can pass today regardless of this design correction because:

- both NODE-73 release refs are still reported unprotected;
- PR #135 currently has no submitted human reviews;
- five-role principal allowlists remain intentionally PENDING;
- canonical `uv.lock` remains stale;
- Hosted CI continues to exhibit pre-execution failures;
- trusted PostgreSQL/Terraform/Staging/Production/six-runtime evidence remains outstanding.

## Verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

This checkpoint deliberately downgrades the earlier single-SHA finalization assumption instead of hiding the architectural contradiction. NODE-73 may advance only after package/assembler/final-decision code is migrated to the non-cyclic V2 model and then validated in a trusted runnable environment.
