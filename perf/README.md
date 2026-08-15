# LUMI Performance Harness

NODE-69 performance evidence is reproducible, versioned, and provider-cost safe.

## Rules

- `perf/profiles/v1/` is the canonical workload set A–G.
- Real-provider ratio is `0` by default. A benchmark must explicitly declare any paid-provider traffic and may not use it in PR CI.
- `perf/budgets/v1.json` contains **targets**, never measured claims.
- Raw results must identify workload version, git SHA, environment, provider mode and timestamps.
- Provider latency is reported separately from LUMI platform overhead.
- PR checks use deterministic local/mock workloads. Production-like load tests are manual and require an explicitly acknowledged target.
- Raw benchmark results are build artifacts/evidence. Do not commit fabricated numbers.

## Result lifecycle

```text
profile + environment + build
  -> load/browser/db/queue measurement
  -> raw result JSON
  -> budget/regression evaluator
  -> capacity report
```

A source-complete harness is not a performance pass. NODE-69 release requires an executed launch workload, API/SSE/DB/Queue/Canvas evidence, leak checks, and a reviewed capacity/cost model.
