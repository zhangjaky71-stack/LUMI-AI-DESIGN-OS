# NODE-73 Release Branch Protection / Repository Governance

Status: **IMPLEMENTED -> VALIDATING -> BLOCKED_EXTERNAL**

Scope: NODE-73 Release Closure only. This evidence does not introduce NODE-74 and does not change the Final Acceptance verdict.

## P0 finding

The release source/provenance chain is now SHA-bound and signer-workflow-bound, but GitHub repository metadata currently reports both NODE-73 release refs as unprotected:

- `release-closure-p0`: `protected=false`, protection disabled.
- `node-73-final-acceptance-release`: `protected=false`, protection disabled.

This is a repository-governance condition, not an application-source defect. The available GitHub connector in this execution context can read branch metadata but does not expose a branch-protection/ruleset mutation action, so this state cannot honestly be claimed fixed from the current tool surface.

## Why this is release-critical

Immutable image digests, `GITHUB_SHA`, signer-workflow constraints, frozen artifacts, and SHA-256 evidence binding prevent a moving branch name from changing the identity of artifacts that have already been frozen.

However, a production-grade final release also needs repository-level governance showing that the release refs themselves cannot be casually rewritten or bypass the release review/control process after the final RC is selected.

NODE-73 therefore treats protected release refs as a first-class Final Acceptance requirement rather than relying only on workflow conventions.

## Implemented fail-closed evidence path

### 1. GitHub branch-protection collector

Added `scripts/capture_release_branch_protection.py`.

The collector queries GitHub's canonical branch metadata for exactly:

- `node-73-final-acceptance-release`
- `release-closure-p0`

It writes schema `LUMI_RELEASE_BRANCH_PROTECTION_V1` containing:

- repository identity;
- capture timestamp;
- exact branch names;
- each branch's `protected` boolean;
- each branch's exact head SHA.

The report is `PASS` only when both required branches report `protected=true`; otherwise it is `BLOCKED_EXTERNAL` and the collector exits non-zero.

The validator can additionally require `release-closure-p0.head_sha` to equal the final `release_candidate.git_sha`.

### 2. Final release manifest freeze

`final/acceptance/release-manifest-template.json` now requires:

```json
"repository_governance": {
  "path": "PENDING",
  "sha256": "PENDING"
}
```

The governance observation must therefore be frozen by repository path and SHA-256 like the other release evidence, rather than being represented by an unaudited checkbox.

### 3. Canonical assembler gate

`scripts/final-acceptance-assembler.py` now requires `--repository-governance` and only accepts governance evidence below `reports/repository-governance/`.

Assembly blocks unless the report proves:

- schema/kind are canonical;
- status is `PASS`;
- repository is exactly `zhangjaky71-stack/LUMI-AI-DESIGN-OS`;
- the exact two NODE-73 release branches are present with no duplicates;
- both branches are `protected=true`;
- both branch heads are exact SHA40 values;
- `release-closure-p0.head_sha == release_candidate.git_sha`.

The accepted governance report is then frozen into the assembled release package by `path + sha256`.

### 4. Final package gate

`scripts/validate_final_acceptance_package.py` independently re-validates the frozen governance file and all of the same semantics before the normal Final Acceptance decision can run.

`.github/workflows/final-acceptance-gate.yml` already executes this package validator immediately before `final-acceptance-gate.py`, so a missing, stale, unprotected, cross-repository, or cross-RC governance report blocks final acceptance.

### 5. Source anti-regression contract

Added `scripts/validate_repository_governance_contract.py` and wired it into the Final Product Acceptance source-contract.

The source contract requires:

- collector self-test PASS with four negative drills;
- `repository_governance.path + sha256` in the canonical release template;
- assembler wiring and protected-branch checks;
- package-validator wiring and final RC head binding;
- assembler negative drills for unprotected branch, repository swap, and release-head SHA swap.

The Final Acceptance workflow also Python-compiles both the collector and governance source contract.

## Negative drills

The combined collector/assembler/package contracts require the following to BLOCK:

- branch protection status false;
- collector/report status not PASS;
- wrong repository;
- missing/duplicate/unexpected release branch;
- malformed branch head SHA;
- `release-closure-p0` head different from the final RC SHA;
- missing or mutated governance evidence SHA-256.

## Current external blocker

At this checkpoint, GitHub branch metadata still reports both required release refs as unprotected. Therefore a real governance capture **must not** produce PASS today.

Required operational sequence before Final Acceptance:

1. finish remaining code and canonical `uv.lock` remediation;
2. select/freeze the exact final RC SHA;
3. enable repository protection/ruleset controls for both NODE-73 release refs using GitHub repository administration;
4. ensure the protected `release-closure-p0` head is exactly the selected RC SHA;
5. run `capture_release_branch_protection.py` and obtain a PASS report;
6. freeze that report into the final release package;
7. only then run Final Product Acceptance.

This sequence intentionally leaves remediation possible before the final RC is frozen, while making protection mandatory at the release decision boundary.

## Commits

- `fa7728c2545d26bb3c07f6df4eb3999116f8c0e4` — branch-protection collector and negative drills.
- `cdfb6836aae0165fcd01b5b79467a6a4a82a4393` — mandatory repository-governance freeze field in release template.
- `2b2d817f3459bd7b27c7e2fd514df2f40233fcbc` — final package protected-ref validation.
- `c4be0b670874220ce72ba067c0b02bf8f614cc39` — canonical assembler governance input and freeze.
- `f9d92ad56857931b7044104b2b2de638df6c9510` — assembler/package governance negative drills.
- `515275f03ebeaab25c64d3437b94b69bb3c7b969` — repository-governance source contract.
- `00f581ab3ac791a6aa4cbc23d043c8efb6e72fde` — Final Acceptance source-contract integration and syntax gate.

## What is not claimed

No branch protection/ruleset has been enabled by these code changes. This execution context has no connector action to mutate GitHub branch protection, and current GitHub metadata explicitly reports `protected=false` for both refs.

No Hosted CI PASS is claimed. The stale canonical `uv.lock`, trusted PostgreSQL/Terraform/Staging/Production evidence, real six-runtime build/attestation execution, and the repository protection setting remain release blockers.

## Verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

The code path now makes repository governance impossible to omit or hand-wave at Final Acceptance, but the actual GitHub protection setting remains an external P0 that must be corrected and captured before release.
