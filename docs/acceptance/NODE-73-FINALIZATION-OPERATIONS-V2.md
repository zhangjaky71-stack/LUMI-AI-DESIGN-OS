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

## 7. Default-branch dispatch registry and strong protection

GitHub only accepts `workflow_dispatch` when the workflow path exists on the repository default branch. NODE-73 now has a dedicated default-branch dispatch registry on `main` for every release-critical workflow listed in `production/release-actions/pins-v1.json`.

Registry policy:

```text
production/release-actions/default-branch-dispatch-registry-v1.json
```

Registry/source validator:

```text
scripts/validate_release_dispatch_registry_contract.py
```

`validate_release_action_pins.py` invokes the registry contract, so release-critical workflow coverage and Action-pin coverage remain one gate.

### 7.1 Registry-only workflows

For eight release-critical workflows, `main` contains a fail-closed discovery stub only. The stub has `workflow_dispatch`, `contents: read`, and an explicit failing `default-branch-registry-only` job.

To execute real release logic, select/dispatch:

```text
ref = release-closure-p0
```

GitHub then uses the workflow version at that ref. Never treat a default-branch registry stub run as release evidence.

### 7.2 Canonical uv.lock bootstrap

`regenerate-uv-lock.yml` is intentionally not a stub. The `main` and `release-closure-p0` copies are the same canonical two-phase workflow.

Run it with:

```text
expected_sha = exact current release-closure-p0 SHA
confirm = REGENERATE_NODE73_UV_LOCK
```

The resolver phase is `contents: read` only and performs `uv lock`, workspace validation, `uv lock --check` and `uv sync --all-packages --frozen`.

Only the second job receives `contents: write`; it does not execute the resolver, `uv sync`, or release-branch Python scripts. It consumes the same-run `uv.lock` artifact, verifies its SHA-256, rechecks the remote branch head, stages only `uv.lock`, and performs a non-force push.

A no-change canonical lock run succeeds without creating an empty commit.

### 7.3 Branch protection mutation

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

The `configure-release-branch-protection.yml` workflow is now discoverable through the default-branch registry, so the earlier “workflow is absent from default branch” bootstrap blocker is closed.

The privileged mutation path remains deliberately separate from the PR preflight:

```text
pull_request:labeled -> PR preflight only, no Administration secret, no mutation
workflow_dispatch     -> privileged mutation, production environment, Admin-write secret
```

The PR preflight stays bounded to PR #135 / exact base-head/repository identity and cannot receive `RELEASE_GOVERNANCE_ADMIN_TOKEN`.

Actual mutation requires:

```text
ref = release-closure-p0
confirm = APPLY_NODE73_RELEASE_PROTECTION
production environment approval
RELEASE_GOVERNANCE_ADMIN_TOKEN with repository Administration write
```

Final Decision uses a separate Administration-read `RELEASE_GOVERNANCE_TOKEN`; it never receives the write credential.

The successful mutation path uploads `branch-protection-apply.json` as runtime evidence. Do not commit that live report back into the Evidence Head.

## 8. Obtain Evidence-Head-bound human approvals

After Evidence Head is final and protection is enabled, real configured principals review PR #135.

At least three distinct non-author humans must satisfy the five roles and separation-of-duties policy. Review `commit_id` must equal Evidence Head.

A new push invalidates the Evidence Head and requires fresh reviews.

Do not convert review comments or issue comments into approval evidence. Canonical authorization consumes submitted GitHub PR reviews only.

## 9. Run Final Product Acceptance

Dispatch the existing `Final Product Acceptance Gate` workflow with:

```text
ref = release-closure-p0
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
actual canonical uv.lock regeneration and frozen all-workspace PASS
GitHub-hosted runner execution recovery
trusted PostgreSQL/migration/integration evidence
real six-runtime build/start/promotion/attestation evidence
Production-like Staging evidence
Production smoke/canary/rollback/DR evidence
strong protection actually applied to both release refs
Administration-read/write governance credentials and production-environment approval
real role principals other than PR author
at least three distinct Evidence-Head human APPROVED reviews
final-decision-v2 accepted=true
```

Default-branch workflow discoverability is no longer listed as a blocker.

Until all mandatory evidence is real and the V2 outer decision returns `accepted=true`:

# KEEP NODE-73 FINAL ACCEPTANCE BLOCKED
