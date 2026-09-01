# NODE-73 Final Decision Live-Control Artifact Binding

Status: **IMPLEMENTED -> VALIDATING -> BLOCKED_EXTERNAL**

Scope: NODE-73 Release Closure only. This evidence does not introduce NODE-74 and does not change the Final Acceptance verdict.

## P0 finding

The Final Acceptance workflow had already been hardened to run live repository-governance and live GitHub human-approval checks before the 46-scenario product gate. However, the resulting `final-decision.json` was still produced by the inner deterministic product gate and did not cryptographically bind the two live-control reports.

That left an artifact-level ambiguity: a standalone invocation of `final-acceptance-gate.py` could produce an acceptance-shaped decision without proving that the live release controls had been executed for that same decision artifact.

## Implemented closure

### Canonical full release-decision wrapper

Added `scripts/final-acceptance-decision.py` as the canonical full NODE-73 release-decision entry point.

The existing `scripts/final-acceptance-gate.py` remains the deterministic inner product/46-scenario evaluator. It is no longer treated as sufficient full release authorization by itself.

The wrapper executes, in one fail-closed process:

1. canonical final-package validation;
2. live GitHub strong repository-governance capture and validation;
3. live GitHub human-authorization re-verification;
4. deterministic 46-scenario product acceptance;
5. final artifact binding and decision-id derivation.

The wrapper cannot reach product acceptance when either live control fails.

### Live repository-governance binding

The wrapper requires `RELEASE_GOVERNANCE_TOKEN`, performs a fresh GitHub capture through `capture_release_branch_protection.py`, validates the exact final RC SHA and strong protection profile, then writes:

`reports/final-acceptance/<release-id>/runtime/repository-governance-live.json`

The final decision records the report's:

- repository path;
- SHA-256;
- schema kind;
- PASS status;
- protection profile;
- exact protected release-head SHA.

### Live human-authorization binding

The wrapper requires `RELEASE_APPROVAL_TOKEN`, loads the frozen provenance-backed `release_authorization`, re-fetches PR #135 and current reviews through `capture_release_authorization.py`, and writes:

`reports/final-acceptance/<release-id>/runtime/release-authorization-live.json`

The final decision records the report's:

- repository path;
- SHA-256;
- schema kind;
- PASS status;
- distinct human approver count;
- role-to-GitHub-actor mapping.

### Canonical input binding

The final decision also records and hashes:

- frozen release manifest;
- frozen acceptance evidence;
- canonical acceptance matrix.

The inner product gate's original decision identifier is preserved separately as `product_decision_id`.

The outer `decision_id` is recomputed from the canonical JSON payload containing product result, canonical input hashes, and both live release-control bindings. The decision identifier therefore changes if any bound control/input changes.

### Output safety

The wrapper accepts output only below `reports/final-acceptance/` and requires the exact filename `final-decision.json`. The output file does not need to pre-exist; the wrapper creates it only after all required live controls and product evaluation complete.

### Canonical workflow entry point

`.github/workflows/final-acceptance-gate.yml` now has one release-decision step:

`Evaluate canonical final decision with live release controls`

That step exposes:

- `RELEASE_GOVERNANCE_TOKEN` from the dedicated Administration-read secret;
- `RELEASE_APPROVAL_TOKEN` from the short-lived workflow `GITHUB_TOKEN`.

Only `final-decision` receives `pull-requests: read`; no PR write permission is granted.

The Final Decision job no longer invokes `final-acceptance-gate.py` directly. It invokes only `final-acceptance-decision.py`, then archives the complete `reports/final-acceptance/**` tree, including the final decision and both live-control reports.

## Anti-regression contract

Added `scripts/validate_final_decision_control_binding.py`.

It requires the canonical wrapper to retain this order:

`package -> live governance -> live authorization -> product gate -> live/control hash binding -> outer decision_id`

It also requires the Final Acceptance workflow to:

- keep `contents: read + pull-requests: read` scoped to final-decision;
- validate the frozen package before the wrapper;
- expose both live-control tokens only to the canonical decision step;
- call `final-acceptance-decision.py` with release/evidence/output;
- archive the complete final-acceptance evidence tree;
- never invoke `final-acceptance-gate.py` directly inside the final-decision job.

The contract is executed by the Final Product Acceptance source-contract and Python-compiled in the same workflow.

## Related source-contract migration

The repository-governance and human-authorization source contracts were migrated from checking the earlier separate workflow steps to checking the canonical wrapper itself. This prevents stale source contracts from failing merely because the live controls moved into one stronger atomic decision path.

## Closure commits

- `e58f0904...` — initial canonical final-decision wrapper.
- `99fb072b...` — allow safe creation of the not-yet-existing `final-decision.json` output while retaining repository-path constraints.
- `85a26ea6...` — final-decision live-control artifact-binding anti-regression contract.
- `77dc02d0...` — Final Acceptance workflow switched to the canonical wrapper.
- `1306c12f...` — repository-governance source contract migrated to wrapper semantics.
- `f0b35310...` — GitHub human-authorization source contract migrated to wrapper semantics.
- `57d63dd5...` — Final Acceptance source-contract now executes and compiles the final-decision binding contract.

## What is not claimed

No Final Acceptance PASS is claimed by this source closure.

The live governance control currently cannot PASS because GitHub still reports both NODE-73 release refs as unprotected. The live human-authorization control currently cannot PASS because PR #135 has zero submitted reviews and the five-role principal allowlists remain intentionally `PENDING`.

The canonical `uv.lock` is still stale. Hosted CI still exhibits the established pre-execution failure pattern, and trusted PostgreSQL/Terraform/Staging/Production/six-runtime execution evidence remains outstanding.

## Verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

The code-addressable artifact-integrity ambiguity is closed: an accepted-looking product matrix result is no longer the canonical full release decision. The canonical final decision now intrinsically binds live repository governance and live human authorization to the exact final artifact and decision identifier.
