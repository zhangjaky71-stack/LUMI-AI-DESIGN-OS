# NODE-73 Finalization Operations V2

Status: **CANONICAL OPERATIONAL ADDENDUM — FINAL ACCEPTANCE STILL BLOCKED**

This document is the operational companion to `NODE-73-FINALIZATION-IDENTITY-V2.md` and supersedes any older NODE-73 instruction that implies live branch-protection or approval results should be committed back into the Evidence Head.

## 1. Non-cyclic identities

Keep two immutable identities separate:

```text
Source RC SHA     = product/runtime commit already built, staged and deployed
Evidence Head SHA = final release-closure-p0 commit containing non-live evidence, policies, package and final-decision source
```

Final Decision must prove Source RC is a Git ancestor of Evidence Head. They normally differ.

## 2. Before Evidence Head freeze

Complete all source-changing remediation first, including the canonical `uv.lock` regeneration. Never hand-edit `uv.lock`.

Do not enable final strong protection while more source/package commits are still required.

Required order:

```text
1. finish source remediation
2. regenerate canonical uv.lock
3. obtain trusted source/lock gate PASS
4. freeze Source RC runtime/cloud evidence
5. prepare real approval principals + operational handoff
6. assemble and validate release-manifest-v2.json
7. commit all non-live final evidence
8. select the resulting release-closure-p0 commit as Evidence Head
```

## 3. Prepare approval policy and request without hand-editing hashes

Canonical generator:

```text
scripts/prepare_release_authorization_request_v2.py
```

It derives Source RC identity from the real Production deployment manifest and generates:

```text
reports/final-acceptance/<release-id>/pre-final/approval-policy-v2.json
reports/final-acceptance/<release-id>/pre-final/authorization-request-v2.json
```

The generator computes the approval-policy SHA-256 automatically and validates the resulting request against the canonical V2 authorization validator.

Role login inputs accept comma-separated real GitHub logins. Do not invent placeholder users.

The package validator rejects an approval policy unless it can statically satisfy:

```text
minimum distinct actors >= 3
PR #135 author excluded
Engineering actor != Security actor
Security actor != Release Owner actor
all five roles assignable from configured allowlists
```

PR #135 author exclusion is modeled statically and is revalidated live against GitHub at Final Decision.

If real principals are unavailable, keep authorization blocked. Do not weaken the policy.

## 4. Assemble the committed V2 package

Use `.github/workflows/assemble-final-acceptance.yml` or the canonical V2 assembler directly.

The committed package must contain only pre-final material:

```text
Source RC identity
Production/upstream/scenario evidence
repository-governance policy
approval policy reference through authorization request
operational handoff
approvals = PENDING for all five roles
```

It must not contain live branch-protection reports, live approval results or final-decision artifacts.

## 5. Freeze Evidence Head

After the package and every non-live source/evidence file are final, commit them to `release-closure-p0`.

Record:

```text
evidence_head_sha = exact release-closure-p0 HEAD
```

Any source commit after this point creates a new Evidence Head and invalidates all Evidence-Head-bound human approvals.

## 6. Require the unique final status check

Canonical required status context:

```text
node73-final-contract-gate
```

The governance policy requires this exact context. Generic or unrelated successful checks cannot satisfy NODE-73 governance.

The Final Product Acceptance workflow checks out exact `github.sha` in source-contract, canonical-lock-gate and final-decision. The `node73-final-contract-gate` job summarizes source-contract + canonical-lock-gate and must succeed before final-decision may run.

Additional stronger required checks are allowed, but this canonical context cannot be removed.

## 7. Apply strong branch protection only after Evidence Head is stable

Canonical policy-driven applicator:

```text
scripts/apply_release_branch_protection.py
```

It applies the same strong profile to:

```text
node-73-final-acceptance-release
release-closure-p0
```

Before any mutation it live-reads both branch heads and refuses to continue unless `release-closure-p0` still equals the selected Evidence Head.

It requires a fine-grained `RELEASE_GOVERNANCE_ADMIN_TOKEN` with repository Administration **write** permission. Final Decision uses a separate Administration **read** token and does not receive the write credential.

### Current-PR bootstrap path

A brand-new `workflow_dispatch` workflow is not usable until that workflow file exists on the default branch. To avoid that bootstrap dependency for PR #135, `.github/workflows/configure-release-branch-protection.yml` also supports:

```text
pull_request activity = labeled
label = node73-apply-protection
PR number = 135
base = node-73-final-acceptance-release
head = release-closure-p0
head repository = zhangjaky71-stack/LUMI-AI-DESIGN-OS
```

The job additionally requires the `production` environment and checks out `github.event.pull_request.head.sha`, not the PR merge SHA.

Do **not** add the label until:

```text
Evidence Head is final
canonical lock/source checks can run successfully
RELEASE_GOVERNANCE_ADMIN_TOKEN is configured
production environment approval is available
node73-final-contract-gate is the intended required context
```

The workflow uploads `branch-protection-apply.json` as a runtime artifact. Do not commit that live report back into the Evidence Head.

## 8. Obtain Evidence-Head-bound human approvals

After Evidence Head is final and protection is enabled, real configured principals review PR #135.

At least three distinct non-author humans must satisfy the five roles and separation-of-duties policy. Review `commit_id` must equal Evidence Head.

A new push invalidates the Evidence Head and requires fresh reviews.

Do not convert review comments or issue comments into approval evidence. Canonical authorization consumes submitted GitHub PR reviews only.

## 9. Run Final Product Acceptance

Dispatch the existing `Final Product Acceptance Gate` workflow from exact `release-closure-p0` Evidence Head using:

```text
release_manifest_path = reports/final-acceptance/<release-id>/release-manifest-v2.json
acceptance_evidence_path = reports/final-acceptance/<release-id>/acceptance-evidence.json
```

The final-decision job cannot run until:

```text
source-contract == success
canonical-lock-gate == success
node73-final-contract-gate == success
```

It then:

```text
validates the V2 package
reads the frozen governance policy
captures strong branch protection live
requires both branches to include node73-final-contract-gate
captures GitHub reviews live
binds reviews to Evidence Head
proves Source RC ancestor of Evidence Head
projects APPROVED statuses in memory only
runs the stable 46-scenario product gate
hash-binds package/evidence/matrix/policy/request/live reports/execution identity
writes final-decision-v2.json
```

## 10. Runtime artifacts are terminal evidence

These are runtime-only:

```text
branch-protection-apply.json
repository-governance-live.json
release-authorization-live.json
final-decision-v2.json
```

Upload them as Actions artifacts. Do not commit them into `release-closure-p0`.

## 11. Current external blockers

At the current NODE-73 checkpoint, source closure does not imply acceptance. At minimum the following still require real external execution/configuration:

```text
canonical uv.lock regeneration
GitHub-hosted runner execution recovery
trusted PostgreSQL/migration/integration evidence
real six-runtime build/start/promotion/attestation evidence
Production-like Staging evidence
Production smoke/canary/rollback/DR evidence
strong protection actually applied to both release refs
Administration-read/write governance credentials as scoped above
real role principals other than PR author
at least three distinct Evidence-Head human APPROVED reviews
```

Until all mandatory evidence is real and the V2 outer decision returns `accepted=true`:

# KEEP NODE-73 FINAL ACCEPTANCE BLOCKED
