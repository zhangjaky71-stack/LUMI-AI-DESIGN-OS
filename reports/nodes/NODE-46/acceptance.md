# NODE-46 Acceptance — Image Generation Pipeline

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

Base: `node-45-asset-intelligence-release`

## Engineering evidence

| Requirement | Evidence | Status |
|---|---|---|
| Structured provider-neutral generation spec | `model.py` | Implemented |
| Seven frozen generation modes | `GenerationMode`, fixture, validator | Implemented |
| NODE-47 edit boundary preserved | `model_gateway_adapter.py`, static validator | Implemented |
| Explicit reference roles | `ImageReference` | Implemented |
| PRODUCT_SCENE identity-role preflight | `pipeline.py` + test | Implemented |
| STYLE_REFERENCE style-role preflight | `pipeline.py` | Implemented |
| Scope-first reference authorization | `asset_intelligence_adapter.py` | Implemented |
| Commercial rights filtering | NODE-45 adapter + test | Implemented |
| Provider-neutral prompt blocks | `prompt.py` | Implemented |
| Model Gateway routing/invoke adapter | `model_gateway_adapter.py` | Implemented |
| Real NODE-22 MockProvider fallback integration | test | Implemented; hosted execution pending |
| Budget-aware variant count | `variants.py` + tests | Implemented |
| Hard dimensions/identity not silently degraded | variant decision + tests | Implemented |
| Root operation idempotency | `repository.py`, `pipeline.py` | Implemented |
| Per-variant paid operation id | UUIDv5 variant operations | Implemented |
| No prompt/semantic creative content cache | operation-only reuse + test/static gate | Implemented |
| Async provider persisted state | `PendingInvocationRecord`, repository | Implemented |
| Async worker recovery | `resume_pending()` + test | Implemented |
| Poll error keeps unknown remote state pending | hardened pipeline | Implemented |
| Output MIME/decode/dimension/checksum gate | `image_validation.py` | Implemented |
| Transparency validation | PNG alpha gate + test | Implemented |
| Provider URL not durable truth | storage adapter + migration check/comment | Implemented |
| Constraint postflight delegate | `validation.py` | Implemented |
| Brand postflight delegate | `validation.py` | Implemented |
| Identity postflight delegate | `validation.py` | Implemented |
| Required validator unavailable fail-closed | `validation.py` + test | Implemented |
| Provider safety hard rejection | `pipeline.py` + test | Implemented |
| Complete constraint snapshot hash | `hashing.py`, Artifact adapter + test | Implemented |
| Artifact DRAFT -> READY/REJECTED | NODE-42 adapter + tests | Implemented |
| Full generation provenance | `GenerationProvenanceSnapshot` + Artifact adapter | Implemented |
| Generic NODE-42 provenance compatibility | `ProvenanceRecord` adapter | Implemented |
| Failed/corrupt provider result keeps cost | cost before output validation + test | Implemented |
| Decimal/numeric financial values | Python Decimal + SQL numeric(20,8) | Implemented |
| Generation lifecycle events | pipeline | Implemented |
| PostgreSQL schema | `0005_image_generation.sql` | Implemented |
| Deterministic synthetic fixture | `node-46-conformance.json` | Implemented |
| Static architecture validator | `validate_image_generation.py` | Implemented; hosted execution pending |
| Dependency-free orchestration benchmark | `benchmark_image_generation.py` | Implemented; hosted execution pending |
| Dedicated four-stage CI | `.github/workflows/image-generation.yml` | Implemented; hosted execution pending |

## Key safety / correctness assertions

1. Provider SDK payload construction does not belong to NODE-46 domain code.
2. Image edits and masks are not NODE-46 modes; they remain NODE-47.
3. Reference asset ids are authorized via tenant/permission/rights scope before paid generation.
4. UNKNOWN rights are not silently promoted for commercial-use policy.
5. Identical creative semantics under a new operation id are not auto-reused as cached output.
6. A repeated paid operation id with changed semantics fails closed.
7. Each selected variant has a stable paid operation id.
8. Budget reduction changes candidate count, not hard output/identity requirements.
9. Provider output refs are temporary inputs; storage key/checksum/ArtifactVersion are durable truth.
10. Required HARD validator outage is a rejection, not a pass.
11. Provider safety block is a HARD rejection.
12. A corrupt or rejected paid provider result remains visible in cost reconciliation.
13. Async poll uncertainty stays pending so the system does not lie about remote completion state.
14. Artifact provenance binds the full constraint snapshot and exact generation provenance snapshot.

## Synthetic fixture honesty

The conformance fixture and MockProvider tests validate control-plane behavior, determinism, idempotency, access/rights gating, fallback orchestration, output validation and provenance plumbing.

They do **not** demonstrate production image-model quality, including:

- Chinese poster text fidelity;
- product/logo preservation quality;
- brand style fidelity;
- real transparent-background quality;
- real provider latency;
- real provider pricing accuracy.

## Live provider benchmark gate

The frozen NODE-46 definition of done requires selected live provider/model benchmark evidence. Production routing remains gated until NODE-23 contains approved benchmark snapshots for at least:

```text
chinese_poster_text_fidelity
product_consistency
brand_style
multiple_aspect_ratios
transparent_asset
cost_latency
fallback
```

No live-provider score is invented in this node. Therefore NODE-46 cannot be marked COMPLETE solely from MockProvider CI.

## Lockfile discipline

`services/image-generation` is intentionally dependency-free and is not added to the root uv workspace in this node. Root `uv.lock` must remain unchanged. Dedicated CI uses the frozen root dev environment and explicit `PYTHONPATH` to run the service, while production packaging can be added only from the pinned Python 3.12/uv environment without hand-editing lock state.

## Hosted validation requirement

Required workflow jobs:

```text
image-generation-contract
image-generation-quality
image-generation-integration
image-generation-benchmark
```

`image-generation-integration` also applies `0001_artifact_engine.sql` and `0005_image_generation.sql` to a fresh PostgreSQL instance.

If GitHub returns the known account billing/spending-limit failure (`runner_id=0`, zero steps), record it as an external blocker. It is neither PASS nor an observed code/test failure.

## Current decision

**IMPLEMENTED / VALIDATING / not COMPLETE**

Blocking completion evidence:

1. hosted workflow must actually execute green;
2. selected live provider/model revisions need approved NODE-23 image-quality benchmark snapshots.

Next after NODE-46 release evidence: NODE-47 Image Edit.
