# NODE-45 Acceptance — Asset Intelligence

## Status

`IMPLEMENTED / VALIDATING`

Hosted GitHub Actions PASS is not claimed until the dedicated workflow runs on an allocated runner.

## Delivered

- independent `lumi_asset_intelligence` workspace runtime;
- NODE-18 READY Asset and current-rights fact-source boundary;
- NODE-23 version-pinned multimodal embedding capability contract;
- asynchronous/idempotency-addressed asset-analysis and reindex-build job boundaries;
- user > system > auto metadata precedence with auto provenance/confidence;
- OCR spans, object/region evidence, semantic description/tags, pHash and embedding records;
- exact/perceptual/semantic duplicate tiers with semantic non-delete invariant;
- scope-first tenant/project/brand/permission/rights candidate retrieval before scoring;
- current Asset/rights recheck in PostgreSQL retrieval before scoring;
- explainable text/OCR/semantic/similar-to/hybrid search;
- Agent resolver with rights/source/approval evidence and mandatory confirmation;
- selected/approved/rejected ranking feedback without training-authorization side effects;
- atomic per-tenant index version allocation;
- isolated reindex build, coverage comparison, audited promotion and expected-active CAS;
- one ACTIVE index per tenant database invariant;
- deletion mark/reconcile lifecycle;
- NODE-44 active-analysis adapter;
- forward migration `20260817_0014` on `20260817_0013`;
- authenticated nine-route v1 facade;
- deterministic semantic/OCR/rights/duplicate eval corpus;
- dedicated static validator, CI and five-gap production ledger.

## Local evidence

Observed against the final isolated NODE-45 candidate before GitHub publication:

```text
7 passed in 0.25s
NODE45_ASSET_INTELLIGENCE_EVAL_PASS cases=9
NODE45_ASSET_INTELLIGENCE_RUNTIME_SMOKE_PASS
index_version=1 coverage=1 top_score=0.7000
NODE45_ASSET_INTELLIGENCE_VALIDATION_PASS
required_endpoints=9
fixture_cases=9
production_gaps=5
NODE45_PYTHON_COMPILEALL_PASS
NODE45_AST_PARSE_PASS files=22
NODE45_LINE_WIDTH_PASS files=22
```

The compact final suite comprises six broad service/runtime contract tests plus one real NODE-44 adapter integration test; the service tests aggregate the same search, rights, duplicate, async-job, reindex, deletion, drift and concurrency behaviors validated during development.

No live PostgreSQL/pgvector service, real OCR/vision/embedding provider, durable queue worker, real-world retrieval calibration, repository-pinned Python 3.12/uv, Ruff, Pyright or hosted CI PASS is claimed from the isolated environment.

## Database qualification

Migration `20260817_0014` creates version counters, index snapshots, derived analysis records and usage signals. Database triggers validate same-tenant Asset/Index/Project/Brand/Embedding relationships. A partial unique index guarantees at most one ACTIVE index per organization. Usage feedback is database-constrained from becoming a training-authorization grant.

The PostgreSQL repository serializes activation by locking the organization row and comparing the currently active index with the promotion decision's expected active index. Candidate retrieval rechecks live Asset readiness/deletion and current rights/commercial-use before rows enter application ranking.

A real PostgreSQL migration, pgvector round-trip, concurrent version reservation/promotion and representative load test remain production gates.

## Production gaps

Exactly five are tracked in `gap-ledger.json`.

Next node: **NODE-46 — Image Generation**.
