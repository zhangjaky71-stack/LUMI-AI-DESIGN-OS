# NODE-73 Final Approval Provenance Closure

Status: **IMPLEMENTED -> VALIDATING -> BLOCKED_EXTERNAL**

Scope: NODE-73 Release Closure only. This evidence does not introduce NODE-74 and does not change the Final Acceptance verdict.

## P0 finding

The original Final Acceptance package represented the five required release approvals as plain strings:

```text
Product = APPROVED
Engineering = APPROVED
Security = APPROVED
Operations = APPROVED
Release Owner = APPROVED
```

Freezing the containing JSON by SHA-256 proves only that the file did not change. It does not prove which human approved, which exact RC they reviewed, whether the approval is still current, or whether a later `CHANGES_REQUESTED` superseded it.

The NODE-73 runbook defined the five roles but did not define an approver identity source. Treating a hand-authored `APPROVED` string as production authorization was therefore an unresolved release-integrity gap.

## Implemented closure

### 1. Fail-closed role identity policy

Added `final/acceptance/release-approval-policy-template.json` with policy `LUMI_RELEASE_APPROVAL_POLICY_V1`.

The policy is bound to:

- repository `zhangjaky71-stack/LUMI-AI-DESIGN-OS`;
- PR `#135`;
- base ref `node-73-final-acceptance-release`;
- head ref `release-closure-p0`.

It defines exactly five roles:

- Product;
- Engineering;
- Security;
- Operations;
- Release Owner.

The template intentionally leaves every role's GitHub `allowed_logins` as `PENDING`. The code rejects PENDING, bots and malformed GitHub logins. Real organizational principals must be configured before authorization can pass; no role identity is invented by this closure.

Default policy requires at least three distinct human approvers and enforces these mandatory separation-of-duties pairs:

- Engineering != Security;
- Security != Release Owner.

One real review may satisfy more than one role only when the configured allowlists permit it and the distinct-actor / separation-of-duties policy remains satisfied.

### 2. Frozen authorization request

Added `final/acceptance/release-authorization-request-template.json`.

A real request freezes:

- exact release id;
- exact RC `git_sha`, version and migration head;
- repository and PR identity;
- configured approval policy by `path + sha256`;
- complete operational handoff owners.

The request is not an approval. It is the immutable input that tells the authorization collector which final RC and role mapping are being approved.

### 3. GitHub-backed authorization collector

Added `scripts/capture_release_authorization.py`.

The collector reads the canonical PR and real GitHub submitted reviews. A review counts only when:

- PR #135 is open;
- base/head refs are exact;
- PR head SHA equals the final RC SHA;
- reviewer is a configured role principal;
- reviewer is human and is not the PR author;
- review state is `APPROVED`;
- review `commit_id` equals the exact final RC SHA;
- that approval is the actor's latest decisive review.

`COMMENTED` reviews do not authorize a release. A later `CHANGES_REQUESTED` or `DISMISSED` decisive review prevents an older approval from remaining current.

The collector solves the role assignment against configured allowlists, the minimum distinct-human count and separation-of-duties rules.

A PASS `LUMI_RELEASE_AUTHORIZATION_V1` records, per role:

- human GitHub login;
- review id;
- canonical review URL;
- exact RC commit id;
- submitted timestamp;
- APPROVED state.

It also freezes the authorization request and approval policy by SHA-256 and records the distinct approver count.

### 4. Canonical offline authorization validation

The same collector exposes `validate_authorization_report()`.

Both:

- `scripts/final-acceptance-assembler.py`;
- `scripts/validate_final_acceptance_package.py`

dynamically load this canonical validator rather than maintaining a weaker duplicate approval policy.

The assembler only converts structured GitHub-backed approvals into the five simple `APPROVED` statuses expected by the stable `final-acceptance-gate.py` after provenance validation succeeds.

The final package validator independently re-hashes and re-validates the frozen authorization report and requires the release manifest's simple approval/handoff fields to equal the canonical validator's derived result.

This preserves the mature 46-scenario final-decision interface while removing unauthenticated approval strings as a trust source.

### 5. Live review re-verification at Final Decision

The manual `Final Product Acceptance Gate` now gives only the `final-decision` job:

```text
contents: read
pull-requests: read
```

No PR write permission is granted.

The short-lived `${{ secrets.GITHUB_TOKEN }}` is exposed only to the live authorization step as `RELEASE_APPROVAL_TOKEN`; it is not job-scoped and is not visible to checkout/setup-python or unrelated release steps.

After the frozen package and live repository governance are validated, the workflow re-reads GitHub PR #135 and all current reviews. For every frozen role approval it requires:

- review id still exists;
- actor still matches;
- state is still `APPROVED`;
- commit is still the exact final RC;
- frozen review remains that actor's latest decisive review.

The live result is archived as:

`reports/final-acceptance/runtime/release-authorization-live.json`.

Only after this live review check may `final-acceptance-gate.py` run.

### 6. Source and negative-drill coverage

Added `scripts/validate_release_authorization_contract.py` and wired it into Final Acceptance source validation.

The authorization collector has a pure source self-test with eight negative drills, including:

- stale/wrong-RC review;
- bot role principal;
- insufficient distinct humans;
- wrong PR head SHA;
- approval actor swap;
- approval commit swap;
- missing approval timestamp;
- approval-policy hash tamper.

The assembled final-package contract now uses a provenance-backed synthetic authorization fixture and additionally requires actor/RC/policy mutations to BLOCK even when all 46 product scenarios are PASS.

The release workflow least-privilege contract also requires `pull-requests: read` to remain scoped only to `final-decision` and forbids PR write permission.

## Current external state

At this checkpoint GitHub reports **zero submitted reviews on PR #135**.

The canonical approval-policy template also intentionally contains `PENDING` role principals because no real Product/Engineering/Security/Operations/Release Owner GitHub-login mapping has been supplied or established by repository policy.

Therefore a real `capture_release_authorization.py` run cannot honestly produce PASS today.

Required release sequence:

1. finish all source, canonical `uv.lock`, runtime and cloud remediation;
2. freeze the exact final RC SHA;
3. configure the real GitHub login allowlist for all five release roles;
4. freeze that policy and a complete authorization request;
5. obtain real human APPROVED reviews on PR #135 for the exact final RC;
6. require at least three distinct humans and satisfy mandatory separation of duties;
7. capture and freeze `LUMI_RELEASE_AUTHORIZATION_V1`;
8. assemble the final package;
9. run Final Product Acceptance, which re-verifies the approvals live immediately before product acceptance.

## Closure commits

- `de4d518ac3fd0c8b5d569d03ad26e1ae251e9c4e` — fail-closed approval identity policy template.
- `1d57f61d8adc4ded3c445275c58d1a52b0e652de` — authorization request template.
- `51f7dbbacaef7e439989010e9ebb3c21babdb54f` — initial GitHub-backed authorization collector.
- `a8a69517` — align review reuse semantics with role/SoD policy and retain eight negative drills.
- provenance-backed authorization output template replaces the old bare-string approval template.
- `7b6b3938` — canonical assembler consumes GitHub authorization provenance.
- `1febf44c` — final package validator consumes the same canonical authorization validator.
- `b33f6fe5` — final package contract uses provenance-backed approval fixture and tamper drills.
- `65e83da3` — dedicated release authorization source contract.
- `7d780ed4` — Final Decision live GitHub review re-verification.
- `12036046` — scope PR-review read capability through the release workflow permission contract.
- `c710470a` — NODE-73 runbook updated to the real human authorization procedure.

## What is not claimed

No human release approval is claimed by this source closure.

No role-principal mapping is fabricated. No PR review was created or approved by the assistant. Current PR review count is zero.

No Hosted CI PASS is claimed. The established Hosted runner failure pattern still prevents treating red jobs as executed source/test failures when `steps=null` / `logs_url=null`.

The canonical `uv.lock`, repository branch protection, trusted PostgreSQL/Terraform/Staging/Production evidence, real six-runtime build/attestation execution and final human approvals remain release blockers.

## Verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

The code-addressable approval-provenance ambiguity is closed: plain `APPROVED` strings are no longer an acceptable trust source. The remaining approval gap is intentionally human/external and must be satisfied by real GitHub reviews on the frozen final RC.
