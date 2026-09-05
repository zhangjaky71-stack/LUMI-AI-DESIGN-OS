# NODE-73 — Final Governance Execution Closure

Status: **SOURCE/CODE-ADDRESSABLE CLOSURE IMPLEMENTED; RUNTIME ACCEPTANCE BLOCKED**

This report records the NODE-73 final-governance execution closure after Finalization Identity V2. It does **not** declare Final Acceptance PASS and does not introduce NODE-74.

## 1. Audited external checkpoint

Release-critical hosted execution was sampled at:

```text
repository: zhangjaky71-stack/LUMI-AI-DESIGN-OS
PR: #135
base: node-73-final-acceptance-release
head branch: release-closure-p0
sampled head: 8f52b257712931f344ec1faf237ec83043b69fe8
```

At that checkpoint:

```text
PR submitted reviews: 0
release-closure-p0 protected: false
node-73-final-acceptance-release protected: false
```

These are external governance blockers, not PASS evidence.

## 2. Unique canonical required status check

The frozen repository-governance policy no longer accepts an arbitrary strict check.

Canonical required context:

```text
node73-final-contract-gate
```

Implemented in:

```text
final/acceptance/repository-governance-policy-template.json
scripts/validate_release_governance_policy.py
.github/workflows/final-acceptance-gate.yml
```

The policy permits additional stronger required checks, but every NODE-73 release ref must include the canonical context. Generic/unrelated successful checks cannot satisfy NODE-73 governance.

## 3. Frozen policy -> live GitHub protection binding

Canonical binder:

```text
scripts/validate_live_release_governance_v2.py
```

Final Decision now:

```text
loads the frozen governance-policy ref from release-manifest-v2.json
revalidates its SHA-256 through the package validator
captures both release branches live
reuses the strong branch-protection validator
requires strict status checks
requires node73-final-contract-gate on both release refs
binds live release-closure-p0 head to Evidence Head
records required/observed contexts in final-decision-v2.json
```

The outer decision explicitly hash-binds the frozen governance policy and authorization request in `canonical_inputs`.

## 4. Exact Evidence Head execution and final-check ordering

Final Product Acceptance checks out exact commit identity in:

```text
source-contract
canonical-lock-gate
final-decision
```

Each uses an exact SHA checkout with persisted checkout credentials disabled and verifies the checked-out HEAD.

Final Decision cannot run until:

```text
source-contract == success
canonical-lock-gate == success
node73-final-contract-gate == success
```

This removes the prior scheduling window where Final Decision could start before the canonical required summary check completed.

## 5. Policy-driven branch-protection applicator

Canonical mutation implementation:

```text
scripts/apply_release_branch_protection.py
.github/workflows/configure-release-branch-protection.yml
```

The applicator renders the frozen policy into GitHub branch-protection settings for:

```text
node-73-final-acceptance-release
release-closure-p0
```

Before any protection mutation it live-reads both branch heads and refuses to proceed unless `release-closure-p0` still equals the selected Evidence Head.

Strong controls include:

```text
strict required check = node73-final-contract-gate
admin enforcement
required PR approval
dismiss stale approvals
last-push approval
linear history
conversation resolution
force push disabled
branch deletion disabled
```

After mutation it captures live branch state and runs the same frozen-policy/live-protection binder used by Final Decision.

## 6. High-privilege governance secret boundary

A security review found that an earlier bootstrap design would have exposed an Administration-write PAT to a workflow controlled by the unprotected PR branch. That design was removed.

The canonical workflow now deliberately separates:

```text
pull_request:labeled -> unprivileged PR preflight only
workflow_dispatch     -> privileged mutation only
```

### PR preflight

The only PR event is:

```text
label = node73-protection-preflight
PR number = 135
base = node-73-final-acceptance-release
head = release-closure-p0
head repository = same repository
```

It checks out `github.event.pull_request.head.sha` exactly and runs policy/applicator self-tests. It has:

```text
no production environment
no Administration-write secret
no repository write permission
no branch-protection mutation
```

### Privileged mutation

Actual mutation requires:

```text
workflow_dispatch
github.ref = refs/heads/release-closure-p0
confirm = APPLY_NODE73_RELEASE_PROTECTION
production environment
RELEASE_GOVERNANCE_ADMIN_TOKEN in one mutation step only
```

The mutation job rejects `pull_request` as an entry path. The GitHub `GITHUB_TOKEN` remains read-only; branch-protection mutation is performed only through the separately scoped Administration-write credential.

Because a newly added `workflow_dispatch` workflow is not dispatchable until it exists on the default branch, **current PR #135 cannot safely self-bootstrap Administration-write protection through PR-controlled code**. Current NODE-73 therefore honestly retains an external administrator/default-branch bootstrap requirement instead of weakening the secret boundary.

## 7. V1 workflow bypass closure

Historical V1 scripts may remain for audit compatibility, but no GitHub workflow may execute them.

Repository-wide scanner:

```text
scripts/validate_no_v1_finalization_workflow_bypass.py
```

It rejects executable workflow references to:

```text
scripts/final-acceptance-assembler.py
scripts/validate_final_acceptance_package.py
scripts/final-acceptance-decision.py
```

and requires the canonical V2 package producer/final decision path. It also requires `node73-final-contract-gate` to appear exactly once across workflow display names.

## 8. Human approval feasibility is now pre-final

Canonical validator:

```text
scripts/validate_release_approval_policy_feasibility_v2.py
```

A syntactically valid policy is rejected unless its real principal allowlists can satisfy:

```text
all five roles
minimum >= 3 distinct humans
PR #135 author excluded
Engineering != Security
Security != Release Owner
```

The fixed PR #135 author `zhangjaky71-stack` is excluded from static feasibility candidates and is revalidated live by the GitHub review collector.

`validate_final_acceptance_package_v2.py` now rejects an unsatisfiable principal policy before the committed package can pass.

No real principal set is currently frozen because real approver logins have not been supplied. The template remains intentionally fail-closed.

## 9. Canonical pre-final authorization preparation

Generator:

```text
scripts/prepare_release_authorization_request_v2.py
```

It removes manual JSON/hash construction by:

```text
deriving Source RC from the real Production deployment manifest
accepting real role login allowlists
accepting the eight operational handoff owners
validating principal feasibility
writing approval-policy-v2.json
computing its exact SHA-256
writing authorization-request-v2.json
revalidating the generated request through the canonical authorization validator
refusing overwrite
```

No fabricated principal or handoff data is generated.

## 10. Release supply-chain and least-privilege coverage

The branch-protection workflow is included in the release Action pin policy and release workflow permission contract.

All external Actions in the governance path use approved immutable full commit SHAs.

The permission contract now explicitly fails if:

```text
PR preflight receives RELEASE_GOVERNANCE_ADMIN_TOKEN
PR preflight enters the production secret boundary
PR preflight receives GitHub write permissions
privileged mutation accepts pull_request
Administration-write token is workflow-scoped or injected more than once
```

The consolidated `validate_finalization_v2_contract.py` delegates these boundaries to the dedicated permission contract instead of duplicating stale marker logic.

## 11. Canonical operational order

Canonical operational addendum:

```text
docs/acceptance/NODE-73-FINALIZATION-OPERATIONS-V2.md
```

Required order remains:

```text
finish source changes
regenerate canonical uv.lock
obtain source/lock executable PASS
freeze Source RC runtime/cloud evidence
configure real approval principals + handoff
assemble V2 package with approvals PENDING
commit all non-live evidence
select exact Evidence Head
apply strong release-ref protection through a safe external/default-branch admin path
obtain Evidence-Head-bound human reviews
run Final Product Acceptance from exact Evidence Head
archive live reports/final decision as Actions artifacts only
```

Live protection, approval and final-decision results must never be committed back into the Evidence Head.

## 12. Latest hosted execution observation

Latest release-critical runs sampled for head `8f52b257712931f344ec1faf237ec83043b69fe8`:

```text
Final Product Acceptance Gate: 32339799708
Runtime Image Closure Contract: 32339799568
Staging Acceptance Gate: 32339799861
Production IaC Contract: 32339799661
```

Observed job state:

### Final Product Acceptance Gate

```text
source-contract: failure, steps=null, logs_url=null
canonical-lock-gate: failure, steps=null, logs_url=null
node73-final-contract-gate: failure, steps=null, logs_url=null
final-decision: skipped
```

### Runtime Image Closure Contract

```text
runtime-image-closure: failure, steps=null, logs_url=null
```

### Staging Acceptance Gate

```text
canonical-lock-gate: failure, steps=null, logs_url=null
source-contract: failure, steps=null, logs_url=null
remote-read-only-preflight: skipped
acceptance-decision: skipped
contract-gate: failure, steps=null, logs_url=null
```

### Production IaC Contract

```text
terraform-static: failure, steps=null, logs_url=null
source-contract: failure, steps=null, logs_url=null
contract-gate: failure, steps=null, logs_url=null
```

No checkout, Python, uv, Docker, Terraform, PostgreSQL or application command is evidenced as having started. These runs remain consistent with the established GitHub-hosted execution/account/scheduling blocker and provide neither product-failure diagnostics nor PASS evidence. No rerun is justified while the zero-step pattern persists.

## 13. Remaining mandatory external work

At minimum:

```text
canonical uv.lock regeneration and frozen all-workspace PASS
GitHub-hosted execution recovery
trusted PostgreSQL/migration/runtime acceptance
real six-runtime build/start/promotion/attestation execution
Production-like Staging acceptance
Production smoke/canary/rollback/DR evidence
actual strong protection applied to both NODE-73 release refs
safe external/default-branch Administration-write protection bootstrap
scoped Administration read/write governance credentials
real five-role principal allowlists with >=3 usable non-author humans
Evidence-Head-bound submitted APPROVED reviews
final-decision-v2 accepted=true
```

## 14. Verdict

Source/code-addressable governance execution closure is materially stronger, but external execution and human governance evidence are not complete.

# KEEP NODE-73 FINAL ACCEPTANCE BLOCKED
