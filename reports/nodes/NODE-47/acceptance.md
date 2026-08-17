# NODE-47 Acceptance — Image Edit

## Status

`IMPLEMENTED / VALIDATING`

Hosted GitHub Actions and live-provider visual-quality acceptance are not yet claimed.

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

Observed on the final candidate before GitHub publication:

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

The current local environment does not contain the complete repository-pinned Python 3.12/uv
workspace or live PostgreSQL/provider/storage services. The NODE-47 Model Router integration test
was authored but cannot be collected in the isolated candidate because the full NODE-22 package is
not mounted there (`lumi_model_gateway.memory` is absent). Full Model Gateway, Artifact/Design IR,
Ruff, and Pyright gates therefore remain hosted validation work and are not claimed as local PASS.

## Completion blockers

See `gap-ledger.json`. In particular, synthetic goldens do not prove real model preservation of
products/logos/QR/locked text, nor production mask quality, live DB concurrency, or worker
reconciliation.
