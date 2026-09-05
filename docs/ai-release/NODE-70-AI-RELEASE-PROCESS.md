# NODE-70 — AI Release Process

> Date: 2026-08-15  
> Scope: Model / Prompt / Agent / Skill / Recipe / Critic / Constraint / Context / Routing changes  
> Default decision: **BLOCK unless evidence is complete**

## 1. Release unit

Every candidate must have one immutable manifest. Floating identities such as `latest`, `main`, `dev`, `unknown`, or `*` are invalid.

Required identity fields:

- exact Git SHA;
- Agent version;
- system prompt/template hash;
- every participating Skill version;
- Recipe version;
- Model Router policy version;
- Critic version;
- Constraint policy version;
- Context policy version;
- exact eval-suite versions;
- exact benchmark response-profile identity.

`ReleaseManifest.fingerprint()` produces a deterministic fingerprint over this identity. A release report without this fingerprint is not authoritative.

## 2. Baseline truth

Production release mode compares the candidate against the **exact current production baseline**, not the previous laptop run and not a fixture.

The baseline manifest must:

- identify the exact production Git SHA and AI component versions;
- have `role=baseline`;
- have `source=production`;
- use recorded/live evidence rather than `fixture` evidence;
- point to the exact suite versions used by the candidate comparison.

Fixtures under `evals/fixtures/releases/` exist only to prove gate behavior and are explicitly rejected by `mode=release`.

## 3. Blocking executable suites

`evals/release/policy-v1.json` currently automates these executable datasets:

1. `smoke` — task success, hard constraints, critical safety, cost and latency;
2. `auto-repair` — repair correctness, no unsafe branch overwrite, no unreserved paid side effect, bounded repair loop, cost and latency;
3. `visual-critic` — deterministic critic gate, cost and latency.

The suite gate compares candidate vs baseline using the suite's own declared thresholds. In addition, NODE-70 performs **per-case critical checks** so one critical failure cannot be hidden by an aggregate mean.

Critical per-case metrics are zero-tolerance where present:

- `critical_safety_failures`;
- `constraint_violation_count`;
- `unsafe_branch_overwrite`;
- `paid_without_reservation`;
- `loop_bound_exceeded`.

## 4. Required supplemental evidence

Production mode also requires every entry below to be `PASS` with a non-empty evidence reference:

- Product parity acceptance;
- model/provider benchmark;
- Agent security red-team;
- blind human pairwise visual evaluation;
- shadow evidence;
- canary evidence;
- rollback drill.

The source template is `evals/release/supplemental-evidence-template.json`.

Statistical evidence is required for provider benchmark, human pairwise, shadow and canary. Each must record at least the policy minimum sample size plus an explicit confidence method. `evals/statistics.py` provides deterministic summary and Wilson confidence helpers; it never declares a statistically significant improvement automatically.

## 5. Real-provider budget boundary

Pull Requests never automatically invoke a paid provider.

Manual live preflight requires all of:

```text
LUMI_LIVE_EVAL_ENABLED=1
LUMI_LIVE_EVAL_API_KEY=<secret>
LUMI_LIVE_EVAL_BUDGET_USD=<positive budget>
LUMI_LIVE_EVAL_SUITE_ACK=<exact suite name>
LUMI_LIVE_EVAL_SIDE_EFFECT_MODE=none
```

The requested budget must not exceed the configured maximum. Missing authorization produces `SKIPPED`, not an implicit fallback to live traffic.

The current workflow's live job is **authorization preflight only**. Actual provider execution and provider-specific result ingestion remain required runtime evidence; preflight readiness is not a quality result.

## 6. Shadow contract

Shadow is permitted only when:

- inputs are authorized/de-identified under policy;
- candidate output is not displayed to the user;
- external side effects are disabled;
- destructive tools are disabled;
- an explicit spend budget is set.

Shadow must never execute destructive tools or paid external side effects on behalf of the candidate.

## 7. Canary contract

Canonical stages:

```text
internal -> 5% -> 25% -> 50% -> 100%
```

Advancement requires a green offline release gate and current observations inside guardrails.

Automatic rollback decision is required for:

- provider failure;
- any critical failure;
- release gate no longer green;
- error ratio > 1.2x baseline;
- cost ratio > 1.2x baseline;
- quality delta < -0.02.

The source state machine changes configuration/alias state only. It does not hot-mutate the exact frozen version of an already-running Agent Run.

## 8. Rollback

Rollback points the production alias back to the exact baseline version. Failed rollout evidence is retained.

Before NODE-70 can be marked complete, Staging must prove that the real routing/configuration layer can apply this alias change **without redeploying every service**, where the deployment architecture supports dynamic aliasing.

## 9. Human pairwise evaluation

Design-quality reviews must be blind A/B:

- model/version branding hidden;
- presentation order randomized;
- reviewer identity/audit reference recorded;
- winner A/B/tie recorded;
- comments optional but attributable to the review record;
- sample size and confidence method reported.

User select/reject/edit-depth telemetry is supporting evidence only and must not be treated as an unbiased quality label.

## 10. Release decision command

Production decision generation:

```bash
python3 scripts/ai-release-gate.py \
  --baseline-manifest <baseline.json> \
  --candidate-manifest <candidate.json> \
  --baseline-run smoke=<baseline-smoke.json> \
  --candidate-run smoke=<candidate-smoke.json> \
  --baseline-run auto-repair=<baseline-auto-repair.json> \
  --candidate-run auto-repair=<candidate-auto-repair.json> \
  --baseline-run visual-critic=<baseline-visual-critic.json> \
  --candidate-run visual-critic=<candidate-visual-critic.json> \
  --supplemental-evidence <supplemental.json> \
  --mode release \
  --output reports/ai-releases/<date>/<release-id>/decision.json
```

Exit code `0` means gate pass. Exit code `2` means evaluated and blocked. Invalid/missing evidence fails closed.

## 11. CI layers

`AI Regression Release Gate` contains:

- `source-contract`: dependency-free release semantics and syntax checks;
- `canonical-eval-tests`: frozen repository dependency sync + benchmark/release tests;
- `live-provider-preflight`: manual only;
- aggregate release gate: source and canonical test jobs must both succeed.

A source-contract pass does **not** override a frozen dependency failure.

## 12. STOP SHIP

Do not promote if any of the following is true:

- production baseline manifest is missing or not exact;
- any blocking executable suite fails;
- any per-case critical metric fails;
- supplemental evidence is missing/PENDING;
- statistical evidence does not meet its minimum sample requirement;
- paid live evaluation lacks explicit budget authorization;
- shadow can produce side effects;
- canary guardrail requests rollback;
- production alias rollback has not been tested in Staging;
- canonical repository gates are red.
