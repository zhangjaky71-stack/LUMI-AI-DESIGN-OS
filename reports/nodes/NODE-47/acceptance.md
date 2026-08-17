# NODE-47 Acceptance — Image Edit

## Status

`IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL`

Hosted GitHub Actions PASS and live-provider visual-quality acceptance are not claimed.

## Delivered

- structural-first edit planning with five frozen routes;
- zero provider invocation for supported Design IR edits;
- immutable source Asset + ArtifactVersion binding and repeated source re-authorization;
- source-pixel mask coordinates, source/mask hashes, hard protected-region overlap rejection;
- authenticated high-impact mask approval and broad-change confirmation lifecycle;
- exact-model required-capability filtering in NODE-22 Model Router;
- provider-neutral pixel edit request, sync/async lifecycle and conservative pending recovery;
- NODE-27 remains the sole monetary settlement owner; NODE-47 stores audit cost projection only;
- provider output materialization boundary with durable candidate Asset support;
- fail-closed protected/constraint/brand/identity/QR/OCR/intended-change postflight seams;
- provider safety HARD rejection that protected-pixel compositing cannot erase;
- one protected-pixel compositor retry followed by complete revalidation;
- append-only NODE-42 ArtifactVersion output with main-branch CAS for PASS and review fork for
  REPAIR/REJECT;
- Canvas/Design IR `REPLACE_ASSET` only after PASS;
- full edit provenance including AgentRun/agent/recipe/skill and safety evidence;
- tenant-scoped PostgreSQL spec/job/mask/pending/audit/cost-projection persistence;
- forward migration `20260817_0016` on `20260817_0015`, with fail-closed downgrade when edit history
  exists;
- five authenticated `/api/v1` routes;
- 125-case deterministic A-E control-plane corpus, runtime smoke, static validator, dedicated CI,
  and five-gap ledger.

## Local evidence

Observed on the final normalized candidate before GitHub publication:

```text
14 passed in 0.08s
3 passed in 0.06s
NODE47_LOCAL_EDIT_EVAL_PASS cases=125
visual_quality_claimed=false
NODE47_IMAGE_EDIT_RUNTIME_SMOKE_PASS
structural_provider_calls=0 pixel_provider_calls=1 append_only_candidate=v4
NODE47_IMAGE_EDIT_VALIDATION_PASS
routes=5 golden_cases=125 production_gaps=5
ast_files=28
NODE47_AST_PARSE_PASS files=39
NODE47_LINE_WIDTH_PASS files=41
NODE47_PYTHON_COMPILEALL_PASS
```

The local environment does not contain the complete repository-pinned Python 3.12/uv workspace or
live PostgreSQL/provider/storage services. The NODE-47 Model Router integration test was authored
but cannot be collected in the isolated candidate because the full NODE-22 package is not mounted
there (`lumi_model_gateway.memory` is absent). Full Model Gateway, Artifact/Design IR, Ruff, and
Pyright gates therefore remain hosted validation work and are not claimed as local PASS.

## Hosted acceptance evidence

Implementation head `82905c9769bbb46529cf05673bd075a6656800db` is published on PR #114. The
connected GitHub App can read PR metadata and repository contents and can write the branch, but the
workflow-run read endpoint returns:

```text
403 Resource not accessible by integration
```

The combined-status API returns no visible statuses. Therefore this record does **not** claim that
the dedicated NODE-47 workflow received a runner, executed any step, passed, or failed. Hosted
acceptance evidence is externally unavailable to the current integration and is classified
`BLOCKED_EXTERNAL`; this is not evidence of an Image Edit code, migration, provider, test, Ruff, or
Pyright failure.

Before NODE-47 can be COMPLETE, the dedicated hosted workflow must be inspectable and must execute
the frozen workspace install, NODE-47 runtime/current-stack tests, deterministic eval, smoke,
static validator, compile, gap parse, Ruff, and Pyright. Real provider A-E visual-quality evidence
must also be approved through the production benchmark process.

## Completion blockers

See `gap-ledger.json`. In particular, synthetic goldens do not prove real model preservation of
products/logos/QR/locked text, nor production mask quality, live DB concurrency, or worker
reconciliation.
