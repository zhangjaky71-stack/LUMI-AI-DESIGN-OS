# NODE-73 — Final Governance Execution Closure

Status: **SOURCE/CODE-ADDRESSABLE CLOSURE IMPLEMENTED; RUNTIME ACCEPTANCE BLOCKED**

This report records the NODE-73 final-governance execution closure after Finalization Identity V2. It does **not** declare Final Acceptance PASS and does not introduce NODE-74.

## 1. Checkpoint identity

Source checkpoint audited before this report commit:

```text
repository: zhangjaky71-stack/LUMI-AI-DESIGN-OS
PR: #135
base: node-73-final-acceptance-release
head branch: release-closure-p0
checkpoint head: 8f52b257712931f344ec1faf237ec83043b69fe8
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

The policy permits additional stronger required checks, but every NODE-73 release ref must include the canonical context.

This avoids a false-positive protection profile where an unrelated successful check satisfies release governance, and it avoids depending on a generic duplicated `contract-gate` display name.

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

## 4. Exact Evidence Head execution

Final Product Acceptance now performs exact commit checkout in all three code-consuming jobs:

```text
source-contract
canonical-lock-gate
final-decision
```

Each uses:

```text
ref: ${{ github.sha }}
persist-credentials: false
```

and verifies:

```text
git rev-parse HEAD == GITHUB_SHA
```

`final-decision` additionally uses full Git history for Source-RC ancestry proof.

Final Decision cannot run until:

```text
source-contract == success
canonical-lock-gate == success
node73-final-contract-gate == success
```

This removes the prior scheduling window where Final Decision could start in parallel with the canonical required summary check.

## 5. Policy-driven branch-protection applicator

Canonical mutation implementation:

```text
scripts/apply_release_branch_protection.py
.github/workflows/configure-release-branch-protection.yml
```

The script applies the frozen strong policy to:

```text
node-73-final-acceptance-release
release-closure-p0
```

Before any GitHub protection PUT it live-reads both branch heads and refuses to mutate if `release-closure-p0` no longer equals the selected Evidence Head.

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

Administration-write credential scope remains separate from Final Decision:

```text
mutation: RELEASE_GOVERNANCE_ADMIN_TOKEN, Administration write
final verification: RELEASE_GOVERNANCE_TOKEN, Administration read
```

The mutation workflow itself receives only read-only `GITHUB_TOKEN` permissions and is protected by the `production` environment.

## 6. Current-PR governance bootstrap

A new workflow that exists only on a feature/release branch cannot rely solely on `workflow_dispatch` before the workflow is present on the default branch.

To avoid that bootstrap dependency for PR #135, the governance workflow also supports a tightly bounded PR event:

```text
pull_request activity: labeled
label: node73-apply-protection
PR number: 135
base: node-73-final-acceptance-release
head: release-closure-p0
head repository: same repository
```

For PR events the exact Evidence Head is derived from:

```text
github.event.pull_request.head.sha
```

rather than the PR merge commit SHA.

The label must **not** be applied until the final Evidence Head, canonical lock/source gates, production environment approval and Administration-write secret are ready.

This report does not claim that the label currently exists or that the governance workflow has executed.

## 7. V1 workflow bypass closure

Historical V1 scripts remain in the repository for audit compatibility, but no GitHub workflow may execute them.

Repository-wide scanner:

```text
scripts/validate_no_v1_finalization_workflow_bypass.py
```

It rejects workflow execution of:

```text
scripts/final-acceptance-assembler.py
scripts/validate_final_acceptance_package.py
scripts/final-acceptance-decision.py
```

and requires the canonical V2 package producer/final decision markers. It also requires `node73-final-contract-gate` to appear exactly once across workflow job display names.

## 8. Human approval feasibility is now pre-final

A syntactically valid approval policy is insufficient if its allowlists cannot actually satisfy the release role model.

Canonical feasibility validator:

```text
scripts/validate_release_approval_policy_feasibility_v2.py
```

It statically proves that configured real GitHub principals can satisfy:

```text
all five roles
minimum >= 3 distinct humans
PR #135 author excluded
Engineering != Security
Security != Release Owner
```

The fixed PR #135 author `zhangjaky71-stack` is excluded from feasibility candidates and is revalidated live by the GitHub review collector.

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

## 10. Release Action supply-chain and least-privilege coverage

The branch-protection workflow is included in:

```text
production/release-actions/pins-v1.json
scripts/validate_release_action_pins.py
scripts/validate_release_workflow_permissions.py
```

All external Actions in the governance path are pinned to approved immutable full commit SHAs.

The Administration-write secret is injected into exactly the mutation step; it is not workflow-scoped and is not exposed to checkout/setup/self-test steps.

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
enable strong release-ref protection
obtain Evidence-Head-bound human reviews
run Final Product Acceptance from exact Evidence Head
archive live reports/final decision as Actions artifacts only
```

Live protection, approval and final-decision results must never be committed back into the Evidence Head.

## 12. Latest hosted execution observation

Latest release-critical runs sampled for checkpoint head `8f52b257712931f344ec1faf237ec83043b69fe8`:

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

No checkout, Python, uv, Docker, Terraform, PostgreSQL or application command is evidenced as having started in these failed jobs.

Therefore these runs remain consistent with the established GitHub-hosted execution/account/scheduling blocker. They are neither product failure diagnostics nor PASS evidence. No rerun is justified while this zero-step pattern persists.

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
scoped Administration read/write governance credentials
real five-role principal allowlists with >=3 usable non-author humans
Evidence-Head-bound submitted APPROVED reviews
final-decision-v2 accepted=true
```

## 14. Verdict

Source/code-addressable governance execution closure is materially complete, but external execution and human governance evidence are not.

# KEEP NODE-73 FINAL ACCEPTANCE BLOCKED
