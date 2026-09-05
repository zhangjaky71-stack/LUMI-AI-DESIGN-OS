# NODE-73 — Evidence Head Read-Only Freeze Closure

Status: **SOURCE/GOVERNANCE CONTRACT IMPLEMENTED — LIVE APPLICATION STILL BLOCKED**

This report records the NODE-73 governance hardening that converts the final `release-closure-p0` Evidence Head from a conventionally immutable SHA into a GitHub-enforced read-only branch state before human approval and Final Decision.

It does **not** claim that branch protection or branch locking has been applied live.

## 1. Problem

Finalization Identity V2 already separated:

```text
Source RC SHA
Evidence Head SHA
```

and Final Decision already required live `release-closure-p0` head == exact `GITHUB_SHA`.

However, an unlocked Evidence Head branch could still receive a later push after an early governance capture. Re-reading the branch at the end would reduce the race window but would not make the Evidence Head structurally immutable during the approval/final-decision interval.

## 2. Stronger control

GitHub branch protection supports a branch lock/read-only state. NODE-73 now requires that state for the Evidence Head branch.

Canonical branch-specific policy:

```text
release-closure-p0
  strong protection = required
  head SHA = exact Evidence Head
  lock_branch = true
  allow_fork_syncing = false

node-73-final-acceptance-release
  strong protection = required
  lock_branch = false
  allow_fork_syncing = false
```

The base release branch remains unlocked so the final merge target is not made read-only. The Evidence Head branch is locked so normal pushes cannot change the reviewed/finalized commit after governance freeze.

## 3. Governance policy changes

`final/acceptance/repository-governance-policy-template.json` now requires:

```text
require_evidence_head_locked = true
require_non_evidence_release_branches_unlocked = true
```

`validate_release_governance_policy.py` rejects either property being weakened.

Policy negative drills increased from 10 to 12.

## 4. Live branch-protection capture

`capture_release_branch_protection.py` now records normalized live observations for:

```text
lock_branch
allow_fork_syncing
```

These values become part of the runtime governance evidence instead of being inferred from the applicator request.

## 5. Live V2 governance binding

`validate_live_release_governance_v2.py` now requires:

```text
release-closure-p0.lock_branch == true
release-closure-p0.allow_fork_syncing == false
node-73-final-acceptance-release.lock_branch == false
```

alongside the pre-existing strong-protection and canonical status-context requirements.

The normalized result now exposes:

```text
branch_lock_state
evidence_head_locked = true
evidence_head_lock_policy_bound = true
status_check_policy_bound = true
```

Live-governance negative drills increased from 4 to 7 and include:

```text
unlocked Evidence Head -> BLOCK
locked base release branch -> BLOCK
Evidence Head fork syncing enabled -> BLOCK
```

## 6. Applicator ordering and TOCTOU reduction

`apply_release_branch_protection.py` now renders a different GitHub protection request for each branch.

Application order is deliberately:

```text
1. release-closure-p0
2. node-73-final-acceptance-release
```

Before any mutation it reads both release heads and requires the Evidence Head branch to equal the supplied exact Evidence Head SHA.

Immediately before the Evidence Head protection PUT it performs an additional just-in-time lookup and again requires:

```text
live release-closure-p0 head == exact Evidence Head SHA
```

Only then does it request:

```text
lock_branch = true
allow_fork_syncing = false
```

for `release-closure-p0`.

After the Evidence Head is locked, the applicator configures the base release branch with `lock_branch=false` and then performs a complete live capture plus V2 governance-policy binding.

This is stronger than applying the base first and only checking the Evidence Head afterward, because the branch that must remain immutable is frozen before the remaining governance mutation.

## 7. Final Decision binding

`final-acceptance-decision-v2.py` already hash-binds `repository-governance-live.json`.

It now also projects these fields directly into:

```text
live_release_controls.repository_governance
```

including:

```text
branch_lock_state
evidence_head_locked
evidence_head_lock_policy_bound
```

Therefore an accepted Final Decision must visibly prove that the Evidence Head was read-only under the frozen governance policy.

## 8. Related default-branch TOCTOU hardening

The separate live default-branch dispatch registry was also hardened in the same finalization pass:

```text
main_head_start
-> read all nine workflow stubs by exact main_head_start SHA
-> main_head_end
-> require main_head_end == main_head_start
```

This ensures both finalization mutable references are treated with exact-snapshot semantics:

```text
main registry evidence -> exact stable main snapshot
Evidence Head          -> GitHub-enforced read-only branch after freeze
```

## 9. Source commits

Key commits in this closure:

```text
27f5575d57ad19bf0e8f5bd5af56ecda8da02b0e  exact-main registry snapshot capture
d6a8c5cbf1c9cc3efff4bc4bb96d0e0b0a095234  exact-main anti-regression contract
5196899c300497b0a0bcc5b5b415d8d39e8ca185  expose exact-main snapshot proof
fd8996e696f38b6874c57f1f6fea20889e779c4c  require Evidence Head lock in governance policy
73a3852d2e2ef30067efdf586d642a70da791603  validate lock policy
e4f49ac96dcafe9e9862aa97358fd1543f6e527f  capture live branch lock state
6a65d5b5a741b3a33412483be9a26a6835c07f0f  bind lock state in live governance
c34cf7b02bf2ca03f3af95672b59d82b2f0e7ce8  branch-specific protection requests
3905829585b6b35fdaa393e2041edb02fe8156d3  expose lock state in Final Decision
84ba3e7e593a8f2bb964d17c84d3ef891894ba0b  aggregate lock source contract
f2200ab8fd9f61659c1f222c8b6509d6b6b52db1  lock Evidence Head first with JIT SHA guard
d4c21ef034a337d436042b3f19a9607fa143f4e2  freeze Evidence Head-first order in aggregate contract
5b6b73f95d2b9d1c320187721a63ebd308a44fc4  canonical operations update
```

## 10. Current real status

Implemented at source/governance-contract level:

```text
Evidence Head branch-specific lock policy
live lock-state capture
live policy binding
Evidence Head-first applicator
just-in-time Evidence Head SHA guard
Final Decision lock-state projection/hash binding
```

Not demonstrated live:

```text
strong protection on either NODE-73 release branch
release-closure-p0 lock_branch=true
post-apply live governance PASS
real Evidence-Head human approvals
Final Decision accepted=true
```

At the most recent live observation before this report, both NODE-73 release refs were still `protected=false`. This report does not upgrade that state.

## 11. Verdict

**EVIDENCE HEAD READ-ONLY FREEZE = SOURCE IMPLEMENTED**

**LIVE APPLICATION = BLOCKED_EXTERNAL**

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED**
