# LUMI Benchmark Harness

NODE-05 establishes the repository-owned evaluation contract used before model, agent, prompt, and design changes can be called improvements.

## Modes

- `offline deterministic`: no paid provider key; used by PR CI.
- `recorded replay`: candidate response fixtures feed the same graders without contacting providers.
- `live provider`: preflight-only in NODE-05; requires explicit enablement, API key, and positive budget and otherwise returns `SKIPPED`.
- `human / visual`: protocol slots are reserved for later nodes; deterministic graders remain preferred whenever geometry/schema/hash checks are possible.

## Commands

```bash
make eval-smoke
make eval SUITE=smoke
make eval-live SUITE=image
make eval-report RUN_ID=evals/reports/<run-id>.json
```

`make eval-smoke` runs both the production baseline fixture and candidate fixture, applies the suite release gate, emits JSON + Markdown reports, and exits non-zero on regression.

## Dataset contract

Each suite owns a versioned `suite.json` and immutable version directory such as `v1/cases.json`. Historical cases are never edited in place when semantics change; create a new dataset version instead.

Every case declares explicit metrics and deterministic checks. Every suite declares aggregation strategy, optimization direction, primary metric, and release guardrails. Candidate fixtures may optionally carry trace IDs that can later point at LangSmith runs without making LangSmith the sole score database.

## Live eval safety

NODE-05 does not call any paid model. Live preflight requires all three:

```text
LUMI_LIVE_EVAL_ENABLED=1
LUMI_LIVE_EVAL_API_KEY=<secret>
LUMI_LIVE_EVAL_BUDGET_USD=<positive number>
```

Missing configuration is `SKIPPED`, never reported as `PASS`.
