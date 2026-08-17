# NODE-44 Acceptance — Identity Engine

## Status

`IMPLEMENTED / VALIDATING`

Hosted GitHub Actions PASS is not claimed until an allocated runner executes the dedicated workflow.

## Delivered

- PRODUCT / LOGO P0 identity reference-set contracts;
- CHARACTER and privacy-gated FACE contract boundary;
- immutable versioned reference snapshots with SHA-256 identity;
- atomic per-identity PostgreSQL version counter;
- independent LOGO and PRODUCT multi-signal weighting;
- exact checksum equality as positive-only evidence, not false negative identity proof;
- crop/detection evidence and confidence propagation;
- scenario/version threshold profiles with HARD/SOFT/ADVISORY semantics;
- HARD missing-target/provider/signal/confidence fail-closed behavior;
- deterministic calibration runtime using positive/negative/near-miss data;
- precision/recall/FAR/FRR/F1 calibration report with dataset hash and tenant identity;
- NODE-39 IdentityScore-compatible evidence adapter with low-confidence fail-closed semantics;
- executable NODE-18 Asset readiness/tenant/rights policy boundary;
- executable NODE-45 Asset Intelligence multi-signal adapter;
- PostgreSQL persistence and forward migration `20260817_0013`;
- database snapshot immutability, same-tenant Project/Brand scope guard and FACE privacy constraint;
- authenticated six-route v1 API facade;
- deterministic 16-case product/logo benchmark, calibration report, static validator and five-gap ledger.

## Local evidence

Observed against the exact isolated NODE-44 candidate before GitHub commit:

```text
15 passed in 0.06s
NODE44_IDENTITY_RUNTIME_SMOKE_PASS
reference_version=1 score=99.9859 confidence=0.8555
NODE44_IDENTITY_EVAL_PASS cases=16 accuracy=1.000
NODE44_CALIBRATION_REPORT LOGO threshold=95.769231 precision=1.000 recall=1.000
NODE44_CALIBRATION_REPORT PRODUCT threshold=91.85 precision=1.000 recall=1.000
NODE44_CALIBRATION_REPRO_PASS sha256=6037b074549148e40673794bb587b6d0220767a14806bb25bab9fc719a87594d
NODE44_IDENTITY_ENGINE_VALIDATION_PASS
fixture_cases=16
calibration_reports=2
required_endpoints=6
production_gaps=5
NODE44_PYTHON_COMPILEALL_PASS
NODE44_AST_PARSE_PASS files=21
NODE44_LINE_WIDTH_PASS files=21
```

The deterministic benchmark/calibration corpus is a contract fixture only. Its reported 1.000 accuracy/precision/recall is **not** production model accuracy evidence and is not used to claim a real-world quality SLO.

The suite covers exact/transformed/recolored Logo, product background changes, wrong SKU, low-quality crop, missing target, provider unavailability, immutable versions, FACE privacy, data-driven calibration, actual NODE-39 blocking behavior, pair compare, NODE-45 signal derivation and NODE-18 asset tenant/readiness policy.

The isolated candidate intentionally contains only the inherited files needed for NODE-44 tests. A full FastAPI app import could not be claimed locally because unrelated inherited `api/v1` modules are absent from that isolated copy. NODE-44 route shape is instead AST/static validated here; the dedicated hosted workflow remains the full-repository import/lint/type gate.

No live PostgreSQL service, production NODE-45 model/analyzer, production detector/VLM, real-world calibration corpus, FACE consent/retention program, repository-pinned Python 3.12/uv, Ruff, Pyright or hosted CI PASS is claimed locally.

## Calibration qualification

`reports/nodes/NODE-44/calibration-report.json` is reproducibly generated from the 16-case deterministic corpus. It records exact organization ID, identity type, profile version, dataset hash, selected threshold and confusion-derived metrics. Re-running the generator produced the same SHA-256.

The current contract-corpus thresholds are:

- LOGO: `95.769231`;
- PRODUCT: `91.85`.

These are fixture-derived acceptance thresholds only. Production thresholds remain blocked on governed real-world positive/negative/near-miss corpora tied to pinned provider/analyzer versions.

## Database qualification

`20260817_0013` is a forward migration on `20260817_0012`. It creates reference roots, atomic version counters, immutable reference versions, validation evidence and tenant-qualified calibration reports.

Database protections include:

- immutable identity reference-version trigger;
- Project/Brand same-organization scope trigger;
- FACE must be explicitly authorized, project-scoped and not brand-scoped;
- unique per-identity version numbers;
- validation evidence links to an exact reference version.

A real PostgreSQL migration/concurrency/trigger run remains a production gate; static SQL inspection is not represented as live database evidence.

## Production gaps

Exactly five are tracked in `gap-ledger.json`.

## Hosted acceptance gate

An allocated runner must execute frozen workspace installation, NODE-44 tests, runtime smoke, deterministic benchmark, reproducible calibration report, static validator, migration/runtime compile, Ruff, Pyright and relevant repository gates.

Next node: **NODE-45 — Asset Intelligence**.
