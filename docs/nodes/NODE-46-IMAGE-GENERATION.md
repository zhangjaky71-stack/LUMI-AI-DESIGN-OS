# NODE-46 — Image Generation Pipeline

> Phase: 6 Generation & Quality  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Priority: P0 / CORE PRODUCT  
> Depends on: NODE-22, NODE-23, NODE-27, NODE-42, NODE-45  
> Produces: 多模型图片生成服务、Reference/Variant策略、Artifact/Cost/Provenance闭环

## 1. Goal

NODE-46 upgrades image generation from a provider API call into a production orchestration pipeline. The domain accepts structured design intent, references, constraints, quality and budget; it routes provider execution through NODE-22; validates the returned binary; persists a durable generated file; coordinates constraint/brand/identity postflight; creates a NODE-42 Artifact candidate; and reconciles cost/provenance/events.

## 2. Frozen ownership boundaries

```text
Agent / Recipe
  -> ImageGenerationSpec                     NODE-46
  -> provider-neutral PromptBlocks           NODE-46
  -> model route / provider payload / retry  NODE-22 / 23
  -> provider cost truth                     NODE-27
  -> reference authorization / semantics     NODE-45
  -> constraint postflight                   NODE-39
  -> brand postflight                        NODE-43
  -> identity postflight                     NODE-44
  -> durable Artifact version                NODE-42
```

NODE-46 does not import a provider SDK in its domain core. `image.edit` and mask-edit remain NODE-47 responsibilities.

## 3. Implemented request contract

`services/image-generation/src/lumi_image_generation/model.py` freezes:

```text
ImageGenerationSpec
ImageReference
AuthorizedReference
IdentityRequirement
GenerationConstraint
OutputRequirements
PromptBlocks
GatewayGenerationRequest / Result
ValidatedImage / StoredImage
ValidationFinding / ValidationBundle
GenerationProvenanceSnapshot
GenerationCandidate / GenerationJob
```

`budget_limit_usd` and provider cost use Decimal. Operation/project/task/organization ids are validated. Dimensions, variant count, reference count, constraint count and seed range are bounded.

The semantic hash excludes only `operation_id`, allowing semantic equivalence analysis across intentional operations without turning that equivalence into automatic creative-output caching.

## 4. Generation modes

Frozen V1 modes:

```text
TEXT_TO_IMAGE
REFERENCE_TO_IMAGE
PRODUCT_SCENE
STYLE_REFERENCE
TRANSPARENT_ASSET
BACKGROUND_GENERATION
COMPOSITION_EXPLORATION
```

Model Gateway capability mapping:

```text
TEXT/BACKGROUND/COMPOSITION -> image.generate
REFERENCE/PRODUCT/STYLE     -> image.reference_consistency
TRANSPARENT                 -> image.transparent_background
```

No NODE-47 edit capability is mapped here.

## 5. Structured references

Roles:

```text
IDENTITY
STYLE
COMPOSITION
CONTENT
```

`PRODUCT_SCENE` requires an IDENTITY role; `STYLE_REFERENCE` requires a STYLE role. Reference authorization runs through NODE-45 scope-first candidate retrieval before any paid generation call. Commercial policy can exclude `rights=UNKNOWN` and non-commercial assets.

Authorized reference provenance contains exact asset id/version/checksum/rights and a durable `asset:<id>@<version>` reference. Signed provider/storage URLs are not stable provenance.

## 6. Prompt compilation

`prompt.py` compiles provider-neutral blocks:

```text
objective
content
visual_direction
brand_constraints
identity_requirements
negative_constraints
output_dimensions
template_version
```

The NODE-22 adapter receives these structured blocks. Raw user prompt text is not blindly copied into every provider-native schema.

## 7. Variant / budget strategy

`variants.py` uses Decimal arithmetic and the selected route's one-variant estimate.

Budget reduction may reduce only the candidate count and records:

```text
VARIANT_COUNT_REDUCED_FOR_BUDGET
HARD_DIMENSIONS_AND_IDENTITY_UNCHANGED
```

If one candidate cannot be funded, execution stops before paid invoke. Resolution, transparency and hard identity/constraint requirements are never silently lowered.

## 8. Paid idempotency

`repository.py` binds one semantic GenerationJob to:

```text
(organization_id, operation_id)
```

Rules:

- same operation + same semantic payload -> reuse existing job, no provider reinvoke;
- same operation + changed semantics -> `GENERATION_OPERATION_SEMANTIC_CONFLICT`;
- new operation + same semantic hash -> generate again by default.

Every variant also receives a deterministic UUIDv5 `variant_operation_id` for NODE-20/22/27 paid-call idempotency and reconciliation.

## 9. Sync + async provider lifecycle

`pipeline.py` implements:

```text
reference authorization
-> prompt compilation
-> route estimate
-> budget/variant decision
-> generation.started
-> invoke each variant
-> generation.provider_submitted
-> SUCCEEDED | PROVIDER_PENDING | failure
```

Async calls persist `PendingInvocationRecord` containing the exact provider/model/request identity, per-variant operation and request/result snapshots. `resume_pending()` loads the saved Generation Spec and resumes without process-local state.

## 10. Output integrity

`image_validation.py` checks provider output before durable storage:

- empty/oversize;
- MIME sniff + declared MIME agreement;
- PNG signature/chunks/CRC/IHDR/IDAT decompression/IEND/dimensions/alpha;
- JPEG container/SOF dimensions;
- WebP RIFF/VP8X/VP8L/VP8 dimensions;
- output format;
- exact/min dimensions;
- required transparency;
- SHA-256.

Provider output refs are transient. `storage_key + checksum + MIME + size + dimensions` becomes durable truth.

## 11. Postflight orchestration

`validation.py` coordinates existing validation engines instead of duplicating their logic.

```text
constraints present -> NODE-39 delegate
brand rule set      -> NODE-43 delegate
identity requirement-> NODE-44 delegate
```

A required HARD validator that is unavailable generates `UNAVAILABLE/HARD` and rejects the candidate. Provider safety metadata can create a HARD rejection as well.

## 12. Artifact integration

`artifact_adapter.py` uses actual NODE-42 Python contracts:

```text
Artifact(RASTER_IMAGE)
ArtifactBranch(main)
ArtifactVersion(DRAFT)
ArtifactFile(ORIGINAL)
ProvenanceRecord
DRAFT -> READY | REJECTED
```

Artifact content identity binds the complete constraint snapshot hash, not only HARD constraints. A rejected paid output remains auditable but is not approved.

## 13. Full generation provenance

NODE-42's generic provenance intentionally stores only cross-engine fields. NODE-46 additionally persists a content-addressed `GenerationProvenanceSnapshot` containing:

```text
provider/model/revision/provider request
prompt hash/template/compilation ref
reference asset versions
seed
size/quality
routing reasons
pricing snapshot + cost + confidence
agent/recipe/skill versions
git SHA
constraint snapshot
brand rule set
identity validation snapshot
provider safety metadata
```

Snapshot id format:

```text
image-generation-provenance:<sha256>
```

## 14. Cost semantics

NODE-22/27 owns reserve/actual provider accounting. NODE-46 adds generation/candidate identity through `CostReconciliationPort`.

Cost reconciliation occurs before downstream binary/brand/identity acceptance, so a provider call that returns a corrupt or rejected image is still financially visible. Ambiguous paid delivery is not blindly retried by NODE-46; Model Gateway's paid guard owns safe retry/fallback semantics.

## 15. PostgreSQL persistence

`db/migrations/0005_image_generation.sql` creates:

```text
image_generation_jobs
image_generation_candidates
image_generation_pending_invocations
image_generation_provenance
image_generation_cost_reconciliation
```

Key constraints:

- unique tenant-scoped root operation;
- unique per-variant operation;
- numeric provider costs, never float;
- resumable provider request identity;
- complete provenance;
- durable storage key rejects URL-shaped values;
- provider output ref explicitly documented as transient/restricted.

## 16. Events

Implemented events:

```text
generation.started
generation.provider_submitted
generation.completed
generation.failed
artifact.version.created
```

## 17. Conformance tests

`services/image-generation/tests/test_image_generation.py` covers:

- synchronous READY Artifact E2E;
- cost + full provenance completeness;
- variant reduction under budget;
- insufficient budget before paid invoke;
- same-operation duplicate retry;
- same-operation semantic conflict;
- same semantics/new operation is not creative content cache;
- async PENDING recovery;
- corrupt provider output while retaining provider cost;
- transparent output alpha requirement;
- HARD validator unavailable fail-closed;
- provider safety hard rejection;
- structured reference-role preflight;
- NODE-45 commercial rights filtering;
- complete constraint snapshot hashing;
- NODE-44 identity snapshot propagation;
- real NODE-22 MockProvider 429 cross-provider fallback.

The conformance fixture is `fixtures/image-generation/node-46-conformance.json`.

## 18. Benchmark boundary

`scripts/benchmark_image_generation.py` measures only dependency-free orchestration planning. It does not claim provider inference or production network/storage latency.

Required live benchmark families remain:

```text
Chinese poster text fidelity
product consistency
brand style
multiple aspect ratios
transparent asset
cost / latency
fallback
```

Selected live provider/model revisions must have NODE-23 benchmark evidence before production routing. Synthetic MockProvider results are never accepted as live model-quality evidence.

## 19. Dedicated CI

`.github/workflows/image-generation.yml` defines:

```text
image-generation-contract
image-generation-quality
image-generation-integration
image-generation-benchmark
```

Integration starts PostgreSQL/pgvector, applies NODE-42 Artifact migration plus NODE-46 migration, and runs Model Gateway / Asset / Artifact / Generation regressions.

## 20. Acceptance status

Engineering implementation is present, but the node remains:

**IMPLEMENTED / VALIDATING / not COMPLETE**

Completion requires both:

1. hosted contract/quality/integration/benchmark gates actually execute green; and
2. selected live image-generation adapters have approved NODE-23 quality benchmark snapshots for production routing.

An external GitHub Actions billing/spending-limit runner failure is recorded as a blocker, never as PASS or an observed code failure.

下一节点：NODE-47 Image Edit。
