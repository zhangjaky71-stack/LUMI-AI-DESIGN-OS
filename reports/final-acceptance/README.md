# LUMI Final Acceptance Evidence Archive

This directory is the immutable evidence archive consumed by NODE-73. It is not a place for mutable `latest` files or informal sign-off notes.

## Required release package

Each candidate uses a unique directory:

```text
reports/final-acceptance/<release-id>/
├─ release-manifest.json
├─ acceptance-evidence.json
├─ final-decision.json
├─ acceptance-matrix.md
├─ benchmark-summary.json
├─ security-summary.md
├─ performance-summary.md
├─ recovery-summary.md
├─ cost-reconciliation.md
├─ browser-e2e.md
├─ known-gaps.md
└─ upstream/
   ├─ security.json
   ├─ recovery.json
   ├─ performance.json
   ├─ ai-regression.json
   ├─ staging-acceptance.json
   └─ production-deployment.json
```

Additional raw artifacts may live elsewhere under `reports/`, `evals/`, `staging/`, `production/` or `docs/`; every PASS reference in the final package freezes its exact repository path and SHA-256.

## Start fail-closed

Generate the initial acceptance evidence skeleton:

```bash
python3 scripts/create-final-acceptance-evidence.py \
  --release-id <release-id> \
  --git-sha <40-char-sha> \
  --version <version> \
  --migration-head <migration-head> \
  --output reports/final-acceptance/<release-id>/acceptance-evidence.json
```

Every scenario starts as `NOT_RUN`. `NOT_RUN` is deliberately not a legal final status, so an untouched skeleton cannot be accepted.

## Final statuses

Only these statuses are valid at decision time:

```text
PASS
FAIL
BLOCKED_EXTERNAL
DEFERRED_NON_CRITICAL
```

Rules:

- every P0 must be `PASS`;
- `FAIL` always blocks;
- Critical/High items cannot be deferred or external-blocked into a green release;
- non-critical defer/block requires `owner`, `reason`, `impact`, `target_release`, and `workaround`;
- every PASS must point to at least one frozen evidence file.

## Normalize upstream gates

Use `final/acceptance/upstream-decision-template.json` as the wrapper contract for Security, Recovery, Performance, AI Regression, Staging Acceptance and Production Deployment decisions.

An upstream wrapper must contain:

```text
decision_id
passed=true
frozen evidence_refs[]
blockers=[]
```

Performance, AI Regression, Staging Acceptance and Production Deployment wrappers also carry the exact release candidate identity. The wrapper itself is then frozen into `release-manifest.json` using its path and SHA-256.

A wrapper does not make an upstream gate true; its evidence refs must resolve to the real gate outputs and reports.

## Freeze the production deployment

`release-manifest.json` also freezes the exact Production deployment manifest under:

```text
reports/production-deployments/<deployment-id>/manifest.json
```

The deployment id and release-candidate SHA/version/migration head must match the final release.

## Freeze acceptance evidence

After all 46 scenarios are given final statuses and evidence refs, compute the SHA-256 of `acceptance-evidence.json` and write the exact path/hash into `release-manifest.json`.

Do not edit the evidence after freezing it. Any edit changes the hash and makes the gate return NO-GO until a new release manifest is intentionally frozen.

## Run the final decision

```bash
python3 scripts/final-acceptance-gate.py \
  --release reports/final-acceptance/<release-id>/release-manifest.json \
  --evidence reports/final-acceptance/<release-id>/acceptance-evidence.json \
  --output reports/final-acceptance/<release-id>/final-decision.json
```

The only successful final headline is:

```text
LUMI AI DESIGN OS — PRODUCT ACCEPTED
```

Any blocker produces:

```text
NOT ACCEPTED — SEE BLOCKING GAPS
```

Never hand-edit `final-decision.json` as a substitute for running the gate.

## Operational handoff

The release manifest must identify owners for:

- on-call;
- support;
- incident commander rotation;
- first-day release watch;
- quality/cost review;
- security/dependency review;
- DR drill;
- capacity review.

All Product, Engineering, Security, Operations and Release Owner approvals must be `APPROVED` before acceptance.

## Immutability rule

Do not create `reports/final-acceptance/latest/` and do not overwrite a previously signed package. A material evidence change creates a new release package and a new final decision.
