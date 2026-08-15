# LUMI Benchmark & AI Release Harness

NODE-05 establishes the repository-owned evaluation contract. NODE-70 extends that harness into a fail-closed AI production release gate for Model, Prompt, Agent, Skill, Recipe, Critic, Constraint, Context, and routing changes.

## Modes

- `offline deterministic`: no paid provider key; used by PR/source validation.
- `recorded replay`: candidate response fixtures feed deterministic graders without contacting providers.
- `live provider`: manual authorization preflight only until a provider-specific benchmark executor is invoked; never automatic on Pull Requests.
- `human / visual`: blind pairwise evidence required by NODE-70 for production visual-quality release decisions.
- `release`: exact production baseline vs exact candidate plus all supplemental evidence.

## Benchmark commands

```bash
make eval-smoke
make eval SUITE=smoke
make eval-live SUITE=image
make eval-report RUN_ID=evals/reports/<run-id>.json
```

`make eval-smoke` runs both the production-shaped baseline fixture and candidate fixture, applies the suite gate, emits JSON + Markdown reports, and exits non-zero on regression. Fixtures are test evidence only.

## NODE-70 source contract

```bash
python3 scripts/validate_ai_release_contract.py
```

This dependency-free validator checks:

- blocking executable suites can load versioned cases;
- immutable release-manifest semantics;
- clean fixture comparison passes contract mode;
- one critical per-case failure blocks release even if aggregate scores are unchanged;
- fixture evidence is rejected by production release mode;
- shadow has zero side effects;
- canary/rollback rules;
- live evaluation is disabled by default.

## Production release decision

Use `scripts/ai-release-gate.py` with exact baseline/candidate manifests and reports for every blocking suite. Production mode also requires the supplemental evidence declared by `release/policy-v1.json`.

Example shape:

```bash
python3 scripts/ai-release-gate.py \
  --baseline-manifest baseline.json \
  --candidate-manifest candidate.json \
  --baseline-run smoke=baseline-smoke.json \
  --candidate-run smoke=candidate-smoke.json \
  --baseline-run auto-repair=baseline-auto-repair.json \
  --candidate-run auto-repair=candidate-auto-repair.json \
  --baseline-run visual-critic=baseline-visual-critic.json \
  --candidate-run visual-critic=candidate-visual-critic.json \
  --supplemental-evidence supplemental.json \
  --mode release \
  --output reports/ai-releases/<date>/<release-id>/decision.json
```

## Dataset contract

Executable suites own a versioned `suite.json` and immutable version directory such as `v1/cases.json`. Historical cases are never edited in place when semantics change; create a new dataset version instead.

Every executable case declares explicit metrics and deterministic checks. Every executable suite declares aggregation strategy, optimization direction, primary metric, and release guardrails. Candidate fixtures may optionally carry trace IDs that can point at LangSmith runs without making LangSmith the sole score database.

Some repository datasets, such as the current `product-parity` and `model-provider` definitions, are specification/benchmark plans rather than executable `SuiteDefinition` datasets. NODE-70 requires their runtime evidence as supplemental release evidence instead of falsely treating the specifications as green executed suites.

## Critical release semantics

Suite aggregates are not enough for STOP-SHIP metrics. NODE-70 checks critical metrics per case so one critical safety/constraint/paid-side-effect failure cannot be hidden by an average.

The production policy is `release/policy-v1.json`.

## Statistical evidence

`statistics.py` provides deterministic sample summaries and Wilson 95% confidence intervals. It records uncertainty but does not automatically claim that a small positive delta is statistically significant.

Provider benchmark, blind human pairwise, shadow, and canary evidence must meet the policy's minimum sample size and name the confidence method used.

## Live eval safety

Live preflight requires all of:

```text
LUMI_LIVE_EVAL_ENABLED=1
LUMI_LIVE_EVAL_API_KEY=<secret>
LUMI_LIVE_EVAL_BUDGET_USD=<positive number>
LUMI_LIVE_EVAL_SUITE_ACK=<exact suite>
LUMI_LIVE_EVAL_SIDE_EFFECT_MODE=none
```

The budget must remain within the configured maximum. Missing or mismatched authorization is `SKIPPED`, never reported as `PASS`.
