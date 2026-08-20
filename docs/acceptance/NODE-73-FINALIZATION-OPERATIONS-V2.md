# NODE-73 Finalization Operations V2

Status: **CANONICAL OPERATIONAL ADDENDUM — FINAL ACCEPTANCE STILL BLOCKED**

This document is the operational companion to `NODE-73-FINALIZATION-IDENTITY-V2.md`. It supersedes older NODE-73 instructions that conflate Source RC with Evidence Head, commit live controls back into the branch, or execute release logic from the default branch.

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
6. assemble and validate release-manifest-v2.json
7. commit all non-live final evidence
8. select the resulting release-closure-p0 commit as Evidence Head
```

Do not enable final strong protection while more source/package commits are required.

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

Do not commit live branch-protection reports, live reviews, live registry reports, or final-decision artifacts.

## 5. Freeze Evidence Head

After every non-live source/evidence file is final, commit them to `release-closure-p0` and record:

```text
evidence_head_sha = exact release-closure-p0 HEAD
```

Any later push creates a new Evidence Head and invalidates Evidence-Head-bound human approvals.

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

No NODE-73 release mutation logic is allowed on `main`.

A run of the `main` stub that exits 64 is expected fail-closed behavior and is **not** product/release evidence.

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

If `uv.lock` is already canonical, no empty commit is created.

### 7.4 Live registry verification

Final Decision runs:

```text
scripts/validate_live_default_branch_dispatch_registry.py
```

using the ephemeral read-only GitHub token.

It live-fetches `main` and requires all nine paths to remain fail-closed. For each workflow it also requires the `workflow_dispatch.inputs` schema on `main` to exactly match the hardened Evidence-Head workflow.

Runtime report:

```text
reports/final-acceptance/<release-id>/runtime-v2/default-branch-dispatch-registry-live.json
```

The outer Final Decision hash-binds both this live report and the committed registry policy.

## 8. Apply strong branch protection after Evidence Head is stable

Canonical applicator:

```text
scripts/apply_release_branch_protection.py
```

It applies the frozen profile to:

```text
node-73-final-acceptance-release
release-closure-p0
```

Before mutation it live-reads branch heads and refuses to continue unless `release-closure-p0` still equals the selected Evidence Head.

The workflow is split by trust boundary:

```text
pull_request:labeled -> PR preflight only, no Admin secret, no mutation
workflow_dispatch     -> privileged mutation, production environment, Admin-write secret
```

Actual mutation requires:

```text
ref = release-closure-p0
confirm = APPLY_NODE73_RELEASE_PROTECTION
production environment approval
RELEASE_GOVERNANCE_ADMIN_TOKEN with repository Administration write
```

Final Decision uses separate Administration-read `RELEASE_GOVERNANCE_TOKEN`; it never receives the write credential.

## 9. Obtain Evidence-Head-bound human approvals

After Evidence Head is final and protection is enabled, real configured principals review PR #135.

Requirements:

```text
>= 3 distinct non-author humans
all five roles covered
Engineering != Security
Security != Release Owner
review commit_id == Evidence Head
```

A new push requires fresh reviews. Comments are not approval evidence; only submitted GitHub PR reviews count.

## 10. Run Final Product Acceptance

Dispatch:

```text
ref = release-closure-p0
release_manifest_path = reports/final-acceptance/<release-id>/release-manifest-v2.json
acceptance_evidence_path = reports/final-acceptance/<release-id>/acceptance-evidence.json
```

Final Decision then:

```text
validates the V2 package
captures/validates live branch protection
captures/validates live main dispatch registry
captures Evidence-Head GitHub reviews
proves Source RC ancestor of Evidence Head
projects APPROVED states in memory only
runs the stable 46-scenario product gate
hash-binds package/evidence/matrix/policies/live controls/execution identity
writes final-decision-v2.json
```

## 11. Runtime artifacts are terminal evidence

Runtime-only artifacts include:

```text
branch-protection-apply.json
repository-governance-live.json
default-branch-dispatch-registry-live.json
release-authorization-live.json
final-decision-v2.json
```

Archive them as Actions artifacts. Never commit them back into `release-closure-p0`.

## 12. Current external blockers

Source closure does not imply acceptance. Mandatory real work still includes:

```text
actual canonical uv.lock regeneration and frozen all-workspace PASS
GitHub-hosted runner execution recovery
trusted PostgreSQL/migration/integration evidence
real six-runtime build/start/promotion/attestation evidence
Production-like Staging evidence
Production smoke/canary/rollback/DR evidence
strong protection actually applied to both release refs
Administration-read/write governance credentials + production environment approval
real role principals other than PR author
>= 3 distinct Evidence-Head APPROVED reviews
successful live default-branch registry capture
final-decision-v2 accepted=true
```

Default-branch workflow discoverability is no longer a blocker.

Until all mandatory evidence is real:

# KEEP NODE-73 FINAL ACCEPTANCE BLOCKED
