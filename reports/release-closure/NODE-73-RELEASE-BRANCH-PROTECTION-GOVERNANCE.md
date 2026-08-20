# NODE-73 Release Branch Protection / Repository Governance

Status: **IMPLEMENTED -> VALIDATING -> BLOCKED_EXTERNAL**

Scope: NODE-73 Release Closure only. This evidence does not introduce NODE-74 and does not change the Final Acceptance verdict.

## P0 finding

The release source/provenance chain is SHA-bound, signer-workflow-bound, and attestation-bound, but GitHub repository metadata currently reports both NODE-73 release refs as unprotected:

- `release-closure-p0`: `protected=false`, protection disabled.
- `node-73-final-acceptance-release`: `protected=false`, protection disabled.

This is a repository-governance condition, not an application-source defect. The available GitHub connector can read branch metadata but does not expose a branch-protection/ruleset mutation action, so this state cannot honestly be claimed fixed from the current tool surface.

A second source-level issue was identified during closure: checking only `protected=true` would be too weak because a branch can be protected while still allowing an insufficient review/check policy. The release gate therefore now requires a concrete strong protection profile and re-verifies it live at the Final Decision boundary.

## Strong release protection profile

The canonical policy is defined only once in `scripts/capture_release_branch_protection.py` as `LUMI_RELEASE_PROTECTION_PROFILE_V1`.

For each of the two release refs, a PASS requires all of the following:

- GitHub branch metadata reports `protected=true`.
- Detailed protection data is retrievable from GitHub's branch-protection API.
- Required status checks are enabled, `strict=true`, and at least one concrete check/context is required.
- Protection is enforced for administrators.
- Pull-request reviews are required with at least one approving review.
- Stale approvals are dismissed after a new push.
- The latest reviewable push requires approval by another actor.
- No explicit PR-review bypass actors are allowed.
- Linear history is required.
- Review conversations must be resolved before merge.
- Force pushes are disabled.
- Branch deletion is disabled.

The collector records whether signed commits are also required, but signed commits are an observed hardening field rather than a NODE-73 mandatory condition in this profile. This avoids conflating repository protection closure with a separate commit-signing migration.

## Administration-read evidence token

GitHub's detailed branch-protection endpoint requires repository administration read access. The collector therefore requires a fine-grained token with repository **Administration: read** permission when a protected branch needs detailed policy verification.

The token can be supplied as `RELEASE_GOVERNANCE_TOKEN`; the Final Acceptance workflow consumes it only on the single live-governance verification step. It is not exposed at job scope and is therefore not inherited by checkout/setup-python or unrelated steps.

Missing token, insufficient permissions, HTTP failure, or unavailable detailed protection data all fail closed.

## Implemented evidence path

### 1. Live GitHub governance collector

`scripts/capture_release_branch_protection.py` queries exactly:

- `node-73-final-acceptance-release`
- `release-closure-p0`

For protected branches it additionally queries the detailed branch-protection endpoint and normalizes the strong protection profile above.

The report schema is `LUMI_RELEASE_BRANCH_PROTECTION_V1` and contains:

- repository identity;
- capture timestamp;
- exact branch names;
- branch `protected` state;
- exact branch head SHA;
- normalized `LUMI_RELEASE_PROTECTION_PROFILE_V1` policy details.

The report is PASS only when both required branches satisfy the canonical strong profile. `--expected-release-sha` additionally requires `release-closure-p0.head_sha` to equal the final release candidate SHA.

### 2. Frozen release-package evidence

`final/acceptance/release-manifest-template.json` requires:

```json
"repository_governance": {
  "path": "PENDING",
  "sha256": "PENDING"
}
```

The governance observation is therefore frozen by repository path and SHA-256 like the other release evidence, rather than represented by an unaudited checkbox.

### 3. One canonical policy implementation

Both:

- `scripts/final-acceptance-assembler.py`
- `scripts/validate_final_acceptance_package.py`

dynamically load and call the collector's canonical `validate_report()` implementation. They do not maintain their own weakened copy of the branch-protection rules.

The assembler accepts governance evidence only below `reports/repository-governance/`, validates it against the exact final RC SHA, and freezes its `path + sha256` into the release package.

The package validator re-hashes and re-validates that same frozen file before Final Acceptance.

### 4. Live re-verification at Final Decision

`.github/workflows/final-acceptance-gate.yml` now performs the following order for an actual manual Final Decision:

1. resolve the canonical frozen release/evidence paths;
2. validate the canonical assembled/frozen package;
3. expose `RELEASE_GOVERNANCE_TOKEN` only to the live-governance step;
4. extract the frozen final RC SHA;
5. query GitHub live and write `reports/final-acceptance/runtime/repository-governance-live.json`;
6. require both refs to still satisfy the strong profile and require `release-closure-p0.head_sha == final RC SHA`;
7. only then execute `final-acceptance-gate.py`.

The live governance report is archived with the Final Acceptance workflow artifact.

This closes the gap where a repository-committed JSON file could otherwise claim protection that no longer exists at release time.

### 5. Source anti-regression contracts

`scripts/validate_repository_governance_contract.py` is part of the Final Product Acceptance source-contract and requires:

- collector self-test PASS with 11 negative drills;
- strong-profile policy markers and detailed GitHub protection endpoint usage;
- Administration-read token requirement;
- frozen `repository_governance.path + sha256` in the canonical release template;
- assembler/package reuse of the canonical collector validator;
- assembler negative drills for unprotected branch, repository swap, RC-head swap, and unsafe force-push policy;
- Final Decision order: frozen package validation -> live governance recheck -> product acceptance.

The Final Acceptance workflow also Python-compiles the collector and governance source contract.

## Negative drills

The combined collector/assembler/package contracts require the following classes of mutation to BLOCK:

- branch protection status false;
- collector/report status not PASS;
- wrong repository;
- missing/duplicate/unexpected release branch;
- malformed or cross-RC release head SHA;
- no required status checks;
- non-strict status checks;
- administrators not subject to protection;
- no approving PR review requirement;
- stale reviews not dismissed;
- last-push approval disabled;
- explicit PR bypass actors;
- linear history disabled;
- conversation resolution disabled;
- force pushes enabled;
- branch deletion enabled;
- missing or mutated governance evidence SHA-256;
- missing/insufficient live Administration-read token.

## Current external blocker

At this checkpoint GitHub branch metadata still reports both required release refs as `protected=false`. Therefore a real governance capture must not produce PASS today.

Required operational sequence before Final Acceptance:

1. finish remaining source and canonical `uv.lock` remediation;
2. select/freeze the exact final RC SHA;
3. configure strong branch-protection/ruleset controls for both NODE-73 release refs;
4. provision `RELEASE_GOVERNANCE_TOKEN` with the minimum repository Administration-read scope required to inspect detailed protection policy;
5. ensure protected `release-closure-p0` still points exactly to the selected RC SHA;
6. capture and commit/freeze a PASS governance report;
7. assemble the Final Acceptance package;
8. run Final Product Acceptance, which re-verifies governance live before product acceptance.

This ordering intentionally leaves remediation possible before the final RC is frozen, while making repository governance mandatory at the actual release decision boundary.

## Closure commits

Initial governance closure:

- `fa7728c2545d26bb3c07f6df4eb3999116f8c0e4` — initial branch-protection collector.
- `cdfb6836aae0165fcd01b5b79467a6a4a82a4393` — mandatory governance freeze field.
- `2b2d817f3459bd7b27c7e2fd514df2f40233fcbc` — final package governance validation.
- `c4be0b670874220ce72ba067c0b02bf8f614cc39` — assembler governance input/freeze.
- `f9d92ad56857931b7044104b2b2de638df6c9510` — governance negative drills.
- `515275f03ebeaab25c64d3437b94b69bb3c7b969` — governance source contract.
- `00f581ab3ac791a6aa4cbc23d043c8efb6e72fde` — Final Acceptance source-contract integration.

Strong-profile/live-recheck upgrade:

- `88158d9fece1ea29e64222ba8c90326a4687fb8e` — detailed GitHub protection profile and 11 negative drills.
- `27a3c26cbef22d22ee6b859dfa46ba4d8c1ec343` — package validator reuses canonical governance policy.
- `a84f3d7d1078dde2da97ededf54726602b171cef` — assembler reuses canonical governance policy.
- `0ef1542e010a3f0ef0674cdcc3aab91d0f04189f` — strong-profile assembler/package fixture and force-push drill.
- `0bcab95b66d1ab41d617ea17ec461571efa068d0` — strong governance source contract.
- `2c1b1757296ed0c92e6068c650fac6a82921b406` — Final Decision live GitHub governance re-verification.
- `d4c7b1366ade84f59dd5d7818765780519998712` — source contract enforces live recheck ordering.
- `1fefa1a4d7eeab51b2460a2ae233df2b09d8afab` — scope governance secret to the single verification step.

## What is not claimed

No branch protection/ruleset has been enabled by these code changes. Current GitHub metadata explicitly reports `protected=false` for both NODE-73 release refs.

The existence or configuration of the required `RELEASE_GOVERNANCE_TOKEN` secret is not claimed here; the Final Decision now fails closed if it is absent or insufficient.

No Hosted CI PASS is claimed. The latest sampled PR runs continue to fail before executable steps begin (`steps=null`, `logs_url=null`). The stale canonical `uv.lock`, trusted PostgreSQL/Terraform/Staging/Production evidence, real six-runtime build/attestation execution, repository protection, and final human approvals remain release blockers.

## Verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

The code path now prevents weak, stale, forged, or omitted repository-governance evidence from satisfying Final Acceptance, but the actual GitHub repository controls still have to be configured and proven live before release.
