# NODE-73 Finalization Operations V2

Status: **CANONICAL OPERATIONAL ADDENDUM — FINAL ACCEPTANCE STILL BLOCKED**

This document is the operational companion to `NODE-73-FINALIZATION-IDENTITY-V2.md`. It supersedes older NODE-73 instructions that conflate Source RC with Evidence Head, commit live controls back into the branch, execute release logic from the default branch, leave the final Evidence Head writable during approval/final decision, or treat `environment: production` as sufficient without live environment-governance evidence.

## 1. Non-cyclic identities

Keep two immutable identities separate:

```text
Source RC SHA     = product/runtime commit already built, staged and deployed
Evidence Head SHA = final release-closure-p0 commit containing non-live evidence, policies, package and final-decision source
```

Final Decision must prove Source RC is a Git ancestor of Evidence Head. They normally differ.

## 2. Before Evidence Head freeze

Complete all source-changing remediation first, including canonical `uv.lock` regeneration. Never hand-edit `uv.lock`.

Required order:

```text
1. finish source remediation
2. regenerate canonical uv.lock
3. obtain trusted source/lock gate PASS
4. freeze Source RC runtime/cloud evidence
5. prepare real approval principals + operational handoff
6. configure the real GitHub production environment governance
7. assemble and validate release-manifest-v2.json
8. commit all non-live final evidence and policies
9. select the resulting release-closure-p0 commit as Evidence Head
10. apply strong branch governance and lock Evidence Head read-only
11. obtain Evidence-Head-bound human approvals
12. run Final Product Acceptance
```

Do not enable final branch protection/lock while more source, package, or committed evidence changes are required. The GitHub `production` environment must already exist and satisfy the canonical environment policy before privileged branch-governance mutation or Final Decision is attempted.

## 3. Prepare approval policy and authorization request

Canonical generator:

```text
scripts/prepare_release_authorization_request_v2.py
```

It derives Source RC identity from the Production deployment manifest and generates:

```text
reports/final-acceptance/<release-id>/pre-final/approval-policy-v2.json
reports/final-acceptance/<release-id>/pre-final/authorization-request-v2.json
```

It computes the approval-policy SHA-256 and validates the request. Role inputs must be real GitHub logins; do not invent principals.

The package validator requires the principal policy to be statically satisfiable:

```text
minimum distinct actors >= 3
PR #135 author excluded
Engineering != Security
Security != Release Owner
all five roles assignable
```

If real principals are unavailable, authorization remains blocked.

## 4. Assemble the committed V2 package

Use `.github/workflows/assemble-final-acceptance.yml` or `scripts/final-acceptance-assembler-v2.py`.

The committed package contains pre-final material only:

```text
Source RC identity
Production/upstream/scenario evidence
repository-governance policy
release-authorization request
operational handoff
approvals = PENDING for all five roles
```

Repository-level production-environment policy is committed separately at:

```text
final/acceptance/release-environment-policy-template.json
```

Do not commit live branch-protection reports, live environment reports, live reviews, live registry reports, or final-decision artifacts.

## 5. Freeze Evidence Head

After every non-live source/evidence file is final, commit them to `release-closure-p0` and record:

```text
evidence_head_sha = exact release-closure-p0 HEAD
```

The selected Evidence Head is not considered operationally frozen merely because its SHA was recorded. Before human approval or Final Decision, repository governance must make `release-closure-p0` read-only using the canonical branch-protection applicator.

Required freeze state:

```text
release-closure-p0
  strong protection = enabled
  head SHA = Evidence Head
  lock_branch = true
  allow_fork_syncing = false

node-73-final-acceptance-release
  strong protection = enabled
  lock_branch = false
```

This preserves the merge-target branch while preventing a normal push from changing the Evidence Head during human approval or Final Decision.

Any source/evidence change after selecting the Evidence Head must happen only by deliberately undoing the freeze, producing a new Evidence Head, and repeating governance plus all Evidence-Head-bound approvals. Never treat an unlocked replacement commit as the previously approved Evidence Head.

## 6. Canonical required status check

Required status context:

```text
node73-final-contract-gate
```

The governance policy requires this exact context. Generic or unrelated checks cannot satisfy NODE-73 governance.

Final Product Acceptance checks out exact `github.sha` in `source-contract`, `canonical-lock-gate`, and `final-decision`. Final Decision cannot start until:

```text
source-contract == success
canonical-lock-gate == success
node73-final-contract-gate == success
```

## 7. Default-branch dispatch registry

GitHub requires a `workflow_dispatch` path to exist on the default branch. NODE-73 therefore registers every release-critical workflow path on `main`.

Policy:

```text
production/release-actions/default-branch-dispatch-registry-v1.json
```

Static validator:

```text
scripts/validate_release_dispatch_registry_contract.py
```

### 7.1 `main` is discovery-only

All nine release-critical workflow paths on `main` are fail-closed registry stubs:

```text
workflow_dispatch
contents: read
no environment
no secrets
no external action uses
no write/OIDC/package/attestation capability
default-branch-registry-only
exit 64
```

No NODE-73 release mutation logic is allowed on `main`. A run of the `main` stub that exits 64 is expected fail-closed behavior and is **not** product/release evidence.

### 7.2 Always dispatch the release ref

For real NODE-73 execution, explicitly select:

```text
ref = release-closure-p0
```

GitHub then executes the hardened workflow definition from that ref.

This applies to:

```text
regenerate-uv-lock
build-runtime-image-set
runtime-image-closure-contract
staging-acceptance-gate
production-iac-contract
deploy-production
assemble-final-acceptance
configure-release-branch-protection
final-acceptance-gate
```

### 7.3 Canonical uv.lock regeneration

The real `regenerate-uv-lock.yml` exists only as hardened execution logic on `release-closure-p0`.

Dispatch it with:

```text
ref = release-closure-p0
expected_sha = exact current release-closure-p0 SHA
confirm = REGENERATE_NODE73_UV_LOCK
```

Resolver phase:

```text
contents: read
exact SHA checkout
persist-credentials: false
Python 3.12
uv 0.11.28
uv lock
only uv.lock may change
validate workspace membership
uv lock --check
uv sync --all-packages --frozen
uv run --frozen for release compile verification
PYTHONPYCACHEPREFIX points outside the repository
reject any post-resolver untracked file
re-check that only optional uv.lock changed
freeze uv.lock SHA-256
upload same-run artifact
```

Write phase:

```text
needs successful resolver phase
contents: write
exact SHA checkout
persist-credentials: false
download same-run uv.lock artifact
verify SHA-256
verify only uv.lock differs
no resolver
no uv sync
no release-branch Python execution
re-fetch release-closure-p0
require remote head == expected SHA
stage only uv.lock
non-force push
```

If `uv.lock` is already canonical, no empty commit is created. Canonical lock regeneration must finish before the Evidence Head is locked.

### 7.4 Live registry verification

Final Decision runs:

```text
scripts/validate_live_default_branch_dispatch_registry.py
```

using the ephemeral read-only GitHub token.

It freezes the current `main` head SHA, fetches every registry workflow by that exact SHA, verifies the nine stubs remain fail-closed, requires every `workflow_dispatch.inputs` schema to match the hardened Evidence-Head workflow, and then re-reads `main` to prove the default branch did not move during capture.

Runtime report:

```text
reports/final-acceptance/<release-id>/runtime-v2/default-branch-dispatch-registry-live.json
```

The outer Final Decision hash-binds both this live report and the committed registry policy.

## 8. Production environment governance

The canonical policy is:

```text
final/acceptance/release-environment-policy-template.json
```

It requires the real GitHub environment named `production` to satisfy:

```text
minimum required deployment reviewers >= 1
prevent_self_review = true
deployment_branch_policy.protected_branches = true
deployment_branch_policy.custom_branch_policies = false
```

Both privileged branch-protection mutation and Final Decision cross the `environment: production` boundary. The environment must therefore be configured before those operations are attempted.

`RELEASE_GOVERNANCE_ADMIN_TOKEN` is the Administration-write credential used only by the branch-protection applicator. `RELEASE_GOVERNANCE_TOKEN` is a separate Administration-read credential used only by Final Decision. Both must be treated as production-environment secrets; neither belongs at workflow scope or in PR-controlled preflight jobs.

Final Decision also receives only these ephemeral repository reads from `GITHUB_TOKEN`:

```text
contents: read
actions: read
pull-requests: read
```

`actions: read` is scoped to Final Decision so the production environment metadata can be live-read; it is not a repository mutation capability.

Canonical live verifier:

```text
scripts/validate_live_release_environment_v1.py
```

Runtime report:

```text
reports/final-acceptance/<release-id>/runtime-v2/production-environment-live.json
```

Final Decision hash-binds both the committed environment policy and this live report. `environment: production` alone is not acceptance evidence: the live report must prove the reviewer, self-review, and branch-policy rules are actually present.

## 9. Apply strong branch governance and read-only Evidence Head

Canonical applicator:

```text
scripts/apply_release_branch_protection.py
```

The policy is branch-specific:

```text
release-closure-p0
  canonical strong protection
  lock_branch = true
  allow_fork_syncing = false

node-73-final-acceptance-release
  canonical strong protection
  lock_branch = false
  allow_fork_syncing = false
```

The Evidence Head is locked; the merge-target release branch remains unlocked.

The privileged applicator executes in fail-closed order:

```text
1. read both release-branch heads
2. require release-closure-p0 == selected Evidence Head
3. immediately before mutation, re-read release-closure-p0
4. require it still equals the Evidence Head
5. apply Evidence Head protection first with lock_branch=true
6. apply base release-branch protection with lock_branch=false
7. capture both branches live
8. run validate_live_release_governance_v2.py
9. require canonical status checks + strong protection + branch-specific lock state
```

This Evidence-Head-first sequence minimizes the mutation race window and prevents a normal later push after the live governance binder succeeds.

The workflow remains split by trust boundary:

```text
pull_request:labeled -> PR preflight only, no Admin secret, no mutation
workflow_dispatch     -> privileged mutation, production environment, Admin-write secret
```

Actual mutation requires:

```text
ref = release-closure-p0
confirm = APPLY_NODE73_RELEASE_PROTECTION
production environment protection rules satisfied
RELEASE_GOVERNANCE_ADMIN_TOKEN with repository Administration write
```

Final Decision uses separate Administration-read `RELEASE_GOVERNANCE_TOKEN`; it never receives the write credential.

A successful runtime governance report must expose at least:

```text
branch_lock_state.release-closure-p0 = true
branch_lock_state.node-73-final-acceptance-release = false
evidence_head_locked = true
evidence_head_lock_policy_bound = true
status_check_policy_bound = true
```

## 10. Obtain Evidence-Head-bound human approvals

Only after the Evidence Head is strongly protected, locked read-only, and live governance has been verified should real configured principals review PR #135.

Requirements:

```text
>= 3 distinct non-author humans
all five roles covered
Engineering != Security
Security != Release Owner
review commit_id == Evidence Head
```

A deliberate unlock/new push means the old approval set is no longer valid for the new Evidence Head. Comments are not approval evidence; only submitted GitHub PR reviews count.

Production-environment deployment approval and PR role approval are separate controls: passing one does not satisfy the other.

## 11. Run Final Product Acceptance

Dispatch:

```text
ref = release-closure-p0
release_manifest_path = reports/final-acceptance/<release-id>/release-manifest-v2.json
acceptance_evidence_path = reports/final-acceptance/<release-id>/acceptance-evidence.json
```

Final Decision then:

```text
waits for production environment protection rules
validates the V2 package
captures/validates live branch protection
requires Evidence Head branch to remain locked read-only
requires merge-target release branch to remain unlocked
captures/validates live production environment governance
captures/validates exact-snapshot main dispatch registry
captures Evidence-Head GitHub reviews
proves Source RC ancestor of Evidence Head
projects APPROVED states in memory only
runs the stable 46-scenario product gate
hash-binds package/evidence/matrix/policies/live controls/execution identity
writes final-decision-v2.json
```

The final decision projects branch lock state, production-environment reviewer/self-review/branch-policy state, dispatch-registry state, and approval provenance directly into `live_release_controls`, in addition to hash-binding the complete runtime reports.

## 12. Runtime artifacts are terminal evidence

Runtime-only artifacts include:

```text
branch-protection-apply.json
repository-governance-live.json
production-environment-live.json
default-branch-dispatch-registry-live.json
release-authorization-live.json
final-decision-v2.json
```

Archive them as Actions artifacts. Never commit them back into the locked Evidence Head.

## 13. Current external blockers

Source closure does not imply acceptance. Mandatory real work still includes:

```text
actual canonical uv.lock regeneration and frozen all-workspace PASS
GitHub-hosted runner execution recovery
trusted PostgreSQL/migration/integration evidence
real six-runtime build/start/promotion/attestation evidence
Production-like Staging evidence
Production smoke/canary/rollback/DR evidence
production environment actually exists and satisfies the committed environment policy
production environment required reviewers are actually configured
prevent-self-review and protected-branch deployment policy are actually enabled
RELEASE_GOVERNANCE_ADMIN_TOKEN exists in the protected production environment with Administration write
RELEASE_GOVERNANCE_TOKEN exists in the protected production environment with Administration read
strong protection actually applied to both release refs
release-closure-p0 Evidence Head lock actually applied and live-verified
real role principals other than PR author
>= 3 distinct Evidence-Head APPROVED reviews
successful live production-environment capture
successful live default-branch registry capture
final-decision-v2 accepted=true
```

Default-branch workflow discoverability is no longer a blocker. Source-level Evidence Head lock support and source-level production-environment governance support do **not** mean either release branch or the production environment is currently configured or passing.

Until all mandatory evidence is real:

# KEEP NODE-73 FINAL ACCEPTANCE BLOCKED
