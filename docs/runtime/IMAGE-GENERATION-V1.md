# Image Generation Pipeline V1

## Purpose

NODE-46 turns a provider-neutral `ImageGenerationSpec` into validated, durable Artifact candidates with explainable routing, cost and provenance. It is generation orchestration, not a thin provider API wrapper.

## Frozen boundaries

1. Agents produce `ImageGenerationSpec`; they do not construct provider-native payloads.
2. NODE-22 Model Gateway owns provider adapters, provider secrets, routing, safe retry/fallback, reservation and provider telemetry.
3. NODE-23 owns model/capability/pricing/benchmark facts used by routing.
4. NODE-27 remains the provider-cost truth; NODE-46 supplies generation/candidate reconciliation identity.
5. NODE-45 authorizes and resolves reference Assets before any generation scoring/invocation.
6. NODE-39/NODE-43/NODE-44 own constraint, brand and identity validation logic. NODE-46 coordinates them and fails closed when required validators are unavailable.
7. NODE-42 owns durable Artifact/Version/File/Provenance semantics.
8. NODE-47 owns `image.edit` and mask-edit protocols. NODE-46 does not introduce a second edit contract.

## Request contract

`ImageGenerationSpec` records:

```text
organization/project/task/operation
purpose + mode
prompt_compilation_ref
objective/content/visual_direction
aspect_ratio + target dimensions
variant_count
references[] with explicit role
identity_requirements[]
brand_rule_set_version
constraints[] with severity + snapshot
quality_profile
budget_limit_usd (Decimal)
output_requirements
agent/recipe/skill/git provenance
optional seed
```

The root `operation_id` is the paid-operation idempotency boundary. Its semantic hash excludes the operation id so equivalent semantics across two deliberate operations can be compared without forcing creative output reuse.

## Generation modes

```text
TEXT_TO_IMAGE              -> image.generate
REFERENCE_TO_IMAGE         -> image.reference_consistency
PRODUCT_SCENE              -> image.reference_consistency
STYLE_REFERENCE            -> image.reference_consistency
TRANSPARENT_ASSET          -> image.transparent_background
BACKGROUND_GENERATION      -> image.generate
COMPOSITION_EXPLORATION    -> image.generate
```

`PRODUCT_SCENE` requires at least one `IDENTITY` reference. `STYLE_REFERENCE` requires at least one `STYLE` reference. Edit/mask capabilities are intentionally absent.

## Reference security

References are not trusted because an Agent supplies an asset id. `AssetIntelligenceReferenceAuthorizer` calls NODE-45's scope-first repository with organization, permission and rights predicates before it produces an `AuthorizedReference`.

Commercial-generation policy can restrict references to `USER_OWNED | LICENSED` plus `commercial_use_allowed=true`. `UNKNOWN` rights are not silently upgraded. A reference durable ref is `asset:<id>@<version>`; signed download URLs never enter stable provenance.

Reference roles are explicit:

```text
IDENTITY
STYLE
COMPOSITION
CONTENT
```

This avoids treating a moodboard as a product-identity reference or vice versa.

## Prompt compilation

The compiler creates provider-neutral blocks:

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

The Model Gateway adapter formats these blocks into `ModelRequest.inputs`. Provider adapters remain responsible for the final provider-native payload.

## Variant and budget strategy

The Router supplies an estimated cost for one representative variant. `choose_variants()` computes the affordable variant count with Decimal arithmetic.

If the requested count exceeds the available budget, only the variant count may be reduced automatically. The decision records:

```text
VARIANT_COUNT_REDUCED_FOR_BUDGET
HARD_DIMENSIONS_AND_IDENTITY_UNCHANGED
```

If the budget cannot fund one candidate, the pipeline stops before paid invocation. It never silently reduces hard dimensions, transparency or identity requirements to fit budget.

Each selected variant receives a deterministic UUIDv5 `variant_operation_id`. This gives NODE-20/22/27 one paid idempotency key per provider call while the root operation still represents the whole generation request.

## Idempotency and creative reuse

Repository identity is `(organization_id, operation_id)`.

- same operation + same semantics -> return existing GenerationJob, no new paid call;
- same operation + different semantics -> fail `GENERATION_OPERATION_SEMANTIC_CONFLICT`;
- new operation + identical semantic hash -> generate again by default.

The last rule is deliberate: creative exploration must not turn a prompt hash into an implicit content cache.

## Sync and async lifecycle

Synchronous path:

```text
SPEC
-> reference authorization
-> prompt compilation
-> route/estimate
-> variant decision
-> Model Gateway invoke
-> output fetch
-> image integrity validation
-> durable object store
-> constraint/brand/identity postflight
-> Artifact DRAFT
-> READY | REJECTED
-> cost/provenance/events
```

Asynchronous path:

```text
invoke -> PENDING + provider_request_id
-> persist PendingInvocationRecord + full spec snapshot
-> worker resume_pending()
-> poll exact provider/model/request
-> PENDING | terminal result
-> same validation/artifact pipeline
```

The pending record locks provider request identity and per-variant paid operation identity. Worker restart does not require process-local state.

## Output integrity

Provider URLs are temporary inputs, never long-term truth. Before durable storage the V1 technical validator checks:

- non-empty/max size;
- MIME sniffing rather than extension trust;
- declared MIME agreement;
- PNG structure/CRC/IDAT decompression/IHDR/dimensions/alpha;
- JPEG container and SOF dimensions;
- WebP RIFF/primary image dimension metadata;
- requested format;
- exact/minimum dimensions;
- required transparency;
- SHA-256 checksum.

After validation the storage adapter writes a durable object key. The Artifact file stores `storage_key + checksum + size + MIME + dimensions`.

## Postflight validation

`CompositeGenerationValidator` does not score brand or identity itself.

- configured constraints -> NODE-39 delegate;
- explicit Brand Rule Set -> NODE-43 delegate;
- identity requirements -> NODE-44 delegate.

If a HARD validator is required but unavailable, the finding is `UNAVAILABLE/HARD`, which rejects the candidate. Provider safety metadata can also create a HARD rejection.

A rejected candidate may still have a durable file and ArtifactVersion for audit/review; it never becomes APPROVED automatically.

## Artifact integration

The NODE-42 adapter creates:

```text
Artifact(type=RASTER_IMAGE)
ArtifactBranch(main)
ArtifactVersion(DRAFT)
ArtifactFile(ORIGINAL)
ProvenanceRecord(generic cross-engine fields)
```

Then postflight gates `DRAFT -> READY | REJECTED`.

The Artifact version binds the **complete generation constraint snapshot hash**, including HARD/SOFT/ADVISORY constraints. NODE-46 also stores a full `GenerationProvenanceSnapshot`, because NODE-42's generic record intentionally does not contain every generation-specific field.

## Generation provenance

The full snapshot records:

```text
generation/candidate/operation/variant
provider/model/model_revision/provider_request_id
prompt hash/template/compilation ref
reference asset versions
seed
width/height/quality
routing reason codes
pricing snapshot
cost + confidence
agent/recipe/skill versions
code git SHA
constraint snapshot
brand rule set version
identity validation snapshot
provider safety metadata
```

Its content-addressed id is `image-generation-provenance:<sha256>`.

## Cost reconciliation

NODE-22 reserves/commits provider cost around paid invocation. NODE-46 adds generation/candidate identity to reconciliation.

Cost is recorded before downstream image validation. Therefore a corrupt provider output or a candidate rejected by identity/brand/constraint validation still retains the provider cost actually incurred.

Ambiguous delivery is not retried or cross-fallbacked by NODE-46. NODE-22's paid invocation guard owns that decision and later adjustment semantics.

## Database

`db/migrations/0005_image_generation.sql` adds:

```text
image_generation_jobs
image_generation_candidates
image_generation_pending_invocations
image_generation_provenance
image_generation_cost_reconciliation
```

Financial values are `numeric`, not float. `(organization_id, operation_id)` is unique. Each variant operation is unique. Provider output references are explicitly transient/restricted; `storage_key` is the durable reference and rejects URL-shaped values.

## Events

```text
generation.started
generation.provider_submitted
generation.completed
generation.failed
artifact.version.created
```

Events carry ids/status/reason metadata, not provider secrets or full prompts.

## Model-quality gate

Synthetic fixtures and MockProvider tests are control-plane evidence only. They do **not** prove:

- Chinese poster text fidelity;
- product identity quality;
- brand style quality;
- transparency quality;
- real provider latency/cost accuracy.

A provider/model must have a NODE-23 benchmark snapshot for the relevant image-generation quality profile before production routing. Required benchmark families are Chinese poster text fidelity, product consistency, brand style, multiple aspect ratios, transparent asset, cost/latency and fallback behavior.

Until selected live adapters are benchmarked on approved real assets, NODE-46 remains not COMPLETE for production routing even if mock E2E is green.

## Validation and CI

Dedicated workflow: `.github/workflows/image-generation.yml`.

Required gates:

```text
image-generation-contract
image-generation-quality
image-generation-integration
image-generation-benchmark
```

Hosted jobs must actually execute green before this node can be marked COMPLETE. A GitHub account/billing failure with `runner_id=0` and zero steps is an external blocker, not code PASS or code failure evidence.
