# NODE-43 Acceptance — Brand Rules Engine

## Status

`IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL`

Hosted GitHub Actions PASS is not claimed.

## Delivered

- machine-readable BrandTokenSet / BrandAssetSet / BrandRuleSet;
- exact HARD / SOFT / ADVISORY severity alignment with NODE-14;
- immutable rule content with controlled DRAFT -> PUBLISHED lifecycle;
- per-brand concurrency-safe PostgreSQL version reservation;
- Brand guide proposal with page-level citations and human review gate;
- invariant preventing INFERRED_PROPOSAL from directly becoming HARD published policy;
- authenticated publish/review actor from RequestContext;
- deterministic color/font/logo/token/contrast compliance;
- font readiness/rights validation through NODE-18 Asset data;
- canonical NODE-14 ConstraintSet bridge compatible with NODE-39;
- compact exact-version BrandContext;
- NODE-34 BrandContextRetrievalSource using trusted project-data semantics;
- ArtifactVersion and AgentRun exact brand rule-set capture columns/triggers;
- PostgreSQL active-rule pointer tenant/brand/published validation;
- migration `20260817_0012`;
- authenticated v1 Brand Rules API;
- deterministic fixture corpus and evaluator;
- dedicated CI, static validator and five-gap ledger.

## Local evidence

Observed against the exact local NODE-43 candidate in the isolated environment:

```text
9 passed in 0.20s
NODE43_BRAND_RULES_RUNTIME_SMOKE_PASS
version=1 hard_rules=1 violations=1
NODE43_BRAND_RULE_EVAL_PASS cases=25
NODE43_BRAND_RULES_VALIDATION_PASS
fixture_cases=25
required_endpoints=7
production_gaps=5
NODE43_PYTHON_COMPILEALL_PASS
NODE43_LINE_WIDTH_PASS files=20
```

The contract suite covers token binding, forbidden color, Logo safe zone and
transform, unavailable font, guide citation/review, exact version snapshots,
font-rights publication denial and NODE-14 severity/parameter bridging.

No live PostgreSQL service, real brand-guide PDF extraction, NODE-44 Identity
Engine, provider-backed VLM/copy grader, repository-pinned Python/uv, Ruff,
Pyright or hosted CI PASS is claimed locally.

## Hosted runner evidence

The first dedicated workflow attempt for PR #110 is run `32022897751`. Its
`brand-rules` job `95366102349` ended before runner allocation with:

```text
status=completed
conclusion=failure
runner_id=0
runner_name=""
steps=[]
```

No checkout, Python setup, uv setup, frozen workspace install, NODE-43 tests,
Context Engine integration test, deterministic eval, static validator,
migration compile, gap parse, Ruff or Pyright step executed. This is classified
as `BLOCKED_EXTERNAL`, consistent with the runner-allocation blocker on the
preceding stacked nodes. It is not a NODE-43 code, migration or test failure.

## Database qualification

`20260817_0012` is a forward migration on `20260817_0011`.

It creates immutable `brand_rule_set_versions`, cited
`brand_guide_proposals`, concurrency-safe `brand_rule_version_counters`, and
adds exact version references to Brand, ArtifactVersion and AgentRun.

Database triggers:

- reject mutation of snapshot content;
- validate active BrandRuleSet belongs to the same tenant/brand and is published;
- capture active BrandRuleSet on ArtifactVersion INSERT;
- capture active BrandRuleSet on AgentRun INSERT.

Downgrade fails closed if exact historical brand references or NODE-43 data
exist.

A real PostgreSQL migration/concurrency/trigger run remains a production gate;
static SQL inspection is not represented as live database evidence.

## Production gaps

Exactly five are tracked in `gap-ledger.json`.

## Hosted acceptance gate

Before NODE-43 can be COMPLETE, an allocated runner must execute frozen
workspace installation, the NODE-43 API/runtime tests, Context Engine
integration test, deterministic eval, static validator, migration compile/ledger
checks, Ruff, Pyright and relevant repository gates. Infrastructure-specific
gaps then require their own real-service evidence.

Next node: **NODE-44 — Identity Engine**.
