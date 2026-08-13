# NODE-07 Acceptance Report

> Status: **COMPLETE**  
> Node: **NODE-07 — Model Provider Matrix**  
> Implementation PR: `#5` — MERGED  
> Implementation Merge Commit: `8f6d2169435e879a1c42ac6d4ba92118f068d0ac`  
> Registry Version: `1.0.0`  
> Observed At: `2026-08-13`  
> Pricing Snapshot Expires: `2026-09-12`  
> Clean CI Run: `31654622745`  
> Secret Scan Run: `31654622779`  
> Dependency Review Run: `31654622764`

---

## 1. Result

NODE-07 is accepted as the provider-neutral model candidate and benchmark contract for LUMI AI Design OS.

The Node records current first-party capability/lifecycle/price facts, creates task-specific candidate sets, and explicitly refuses to invent live quality or latency measurements. No provider/model winner is selected before a LUMI live benchmark is executed with real provider credentials and a positive explicit budget.

## 2. Registry contract evidence

Clean `contracts` job `94306268277` produced:

```text
PASS model provider registry v1.0.0
PASS providers=5 models=28 route_eligible=27
PASS lifecycle=stable:23, preview:4, deprecated:1
PASS official_sources=30 routes=15
PASS benchmark_status=NOT_MEASURED:28
PASS no provider winner selected before LUMI live benchmark
Contract foundation: PASS
```

The same job also revalidated NODE-06:

```text
PASS product parity matrix v1.0.0
PASS categories=7 capabilities=67 sources=17
PASS targets=PARITY:56, SUPERSET:7, DEFER:4, OUT-OF-SCOPE:0
PASS competitor_status=confirmed:56, confirmed_marketing:9, not_confirmed:2
PASS parity_acceptance_cases=56
```

## 3. Accepted model/provider snapshot

```text
providers               5
model records           28
route eligible          27
stable                  23
preview                  4
deprecated               1
first-party sources     30
task routes             15
live measured winners    0
```

Provider scope:

- OpenAI
- Google Gemini API
- Anthropic Claude API
- Black Forest Labs
- Runway API

The registry covers reasoning/multimodal vision, image generation/edit, video generation/edit, text embeddings, multimodal embeddings, plus replaceable OCR-like and rerank routes.

## 4. Lifecycle / truthfulness guarantees

Accepted lifecycle rule:

```text
stable      -> eligible for benchmark and possible primary/fallback after evidence
preview     -> benchmark eligible; production use requires explicit risk/fallback policy
deprecated  -> never route eligible
legacy      -> never route eligible
shutdown    -> never route eligible
```

All 28 records remain:

```text
benchmark_status = NOT_MEASURED
quality          = NOT_MEASURED
latency_ms       = NOT_MEASURED
```

This is intentional and required. Provider marketing labels are not LUMI measurements.

## 5. Candidate route evidence

Accepted 15 candidate routes:

```text
reasoning.director
reasoning.default
reasoning.fast
vision.ocr
retrieval.rerank
image.general
image.hero
image.text_heavy
image.local_edit
image.fast_variants
video.general
video.fast
video.edit
embedding.text
embedding.multimodal
```

Every route has `selected_primary = null` at NODE-07. Preview-only route sets must declare stable fallback candidates.

## 6. Live benchmark contract

`evals/datasets/model-provider/suite.json` remains:

```text
execution_status = SPECIFIED_NOT_RUN
live_policy       = SKIPPED_WITHOUT_PROVIDER_KEY_AND_POSITIVE_BUDGET
```

The future live suite measures:

```text
task_success
constraint_success
quality
latency_ms
cost_usd
failure_rate
```

No live provider benchmark was fabricated for NODE-07.

## 7. Clean PR evidence

| Gate | Run / Job | Result |
|---|---|---|
| Change classification | `31654622745` / `94306230604` | PASS |
| `frontend` | `31654622745` / `94306268376` | PASS |
| `python` | `31654622745` / `94306268273` | PASS |
| `contracts` | `31654622745` / `94306268277` | PASS |
| `integration` | `31654622745` / `94306268290` | PASS |
| `eval-smoke` | `31654622745` / `94306268281` | PASS |
| `secret-scan` | `31654622779` / `94306230644` | PASS |
| Dependency Review | `31654622764` / `94306230685` | PASS |

## 8. Python quality evidence

Python job `94306268273` completed:

```text
Ruff format: PASS — 30 files already formatted
Ruff lint:   PASS — All checks passed
Pyright:     PASS — 0 errors, 0 warnings, 0 informations
Pytest:      PASS — 19 passed, 1 existing non-blocking Starlette deprecation warning
```

The new model-provider regression test executes `scripts/validate_model_provider_matrix.py` and verifies provider/model/lifecycle/source/route counts plus the no-winner-before-benchmark rule.

## 9. CI artifacts

Clean PR run retained:

```text
frontend-ci-logs-31654622745
  Artifact ID: 9163899157
  SHA256: ad2269f7708d3bc9c86ca089aa7df4f7950f198f83769c4c81dce8b8044d62b2

python-ci-logs-31654622745
  Artifact ID: 9163884715
  SHA256: e6ab2b2fafd5ffa0bf53a69f36d0474779bcb93ed6ff601ca7e59bdac5262200

eval-smoke-reports-31654622745
  Artifact ID: 9163878808
  SHA256: d65148665fcfa0a2037977b3e495b606faeee3ae1f98c4e88dbe09b8e03b3ff0
  Retention: 14 days
```

## 10. Accepted deliverables

- `docs/models/provider-sources.json`
- `docs/models/provider-matrix-manifest.json`
- `docs/models/route-candidates.json`
- `docs/models/providers/openai.json`
- `docs/models/providers/google.json`
- `docs/models/providers/anthropic.json`
- `docs/models/providers/black-forest-labs.json`
- `docs/models/providers/runway.json`
- `docs/models/MODEL-PROVIDER-MATRIX.md`
- `config/model-registry.seed.json`
- `evals/datasets/model-provider/suite.json`
- `scripts/validate_model_provider_matrix.py`
- `evals/tests/test_model_provider_matrix_contract.py`
- `make model-provider-validate`
- blocking `contracts` integration

## 11. Refresh policy

The price/lifecycle snapshot expires on `2026-09-12`. Before relying on stale records, NODE-22/23 or a release process must re-read first-party provider docs, update the registry, bump version when semantics change, and re-run affected benchmarks before altering routing policy.

## 12. Definition of Done

```text
provider source snapshot                 PASS
model registry v1                       PASS
price/lifecycle snapshot                PASS
15 task candidate routes                PASS
live benchmark profiles                 PASS
provider adapter contract               PASS
unknowns explicitly NOT_MEASURED        PASS
registry validator                      PASS
CI contract integration                 PASS
NODE-04 quality/security gates          PASS
NODE-05 eval-smoke regression           PASS
NODE-06 parity contract regression      PASS
implementation PR merged                PASS
```

**NODE-07 COMPLETE. Next engineering node: NODE-08 — Canvas Technology Spike.**
