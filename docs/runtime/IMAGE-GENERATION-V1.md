# Image Generation Runtime V1

## Purpose

NODE-46 turns provider-neutral design intent into durable raster candidates without leaking
provider SDK semantics into Agent, Canvas, Artifact or API contracts. The runtime coordinates
preflight authorization, Model Gateway invocation, image integrity checks, domain postflight,
durable storage and Artifact provenance. NODE-47 owns edit/mask workflows.

## Boundary

```text
Agent / API
  -> ImageGenerationSpec
  -> NODE-46 submit (202 / durable job)
  -> NODE-19 worker boundary
  -> current-reference authorization (NODE-18 / NODE-45)
  -> provider-neutral prompt blocks
  -> NODE-22 Model Gateway
       -> NODE-23 capability / model / revision routing
       -> NODE-20 paid side-effect idempotency
       -> NODE-27 reserve + settle + telemetry
  -> provider output fetch
  -> MIME/decode/dimension/checksum/alpha gate
  -> NODE-39 / NODE-43 / NODE-44 postflight delegates
  -> durable object store
  -> NODE-42 Raster ArtifactVersion DRAFT -> READY
```

NODE-46 never constructs provider-native request payloads. It also never writes monetary ledger
truth; `image_generation_cost_projection` is an audit projection whose database contract fixes
`monetary_owner=NODE27_MODEL_GATEWAY_SETTLEMENT`.

## Generation modes

V1 freezes seven creation modes:

- `TEXT_TO_IMAGE`
- `REFERENCE_TO_IMAGE`
- `PRODUCT_SCENE`
- `STYLE_REFERENCE`
- `TRANSPARENT_ASSET`
- `BACKGROUND_GENERATION`
- `COMPOSITION_EXPLORATION`

`IMAGE_EDIT` and `IMAGE_MASK_EDIT` remain NODE-47 capabilities and are intentionally absent from
the NODE-46 adapter mapping.

## Idempotency and paid side effects

The root `(organization_id, operation_id)` identifies a generation request. A semantic mismatch
under the same operation fails closed. Each selected variant receives a deterministic UUIDv5
`variant_operation_id`; NODE-22 passes that identifier through NODE-20 so a paid retry does not
become a new billable creative operation. A new operation id with identical creative semantics is
not automatically served from a prompt/content cache.

## References and rights

Every reference is explicit and has an `IDENTITY`, `STYLE`, `COMPOSITION` or `CONTENT` role.
`PRODUCT_SCENE` requires an identity reference and `STYLE_REFERENCE` requires a style reference.

Authorization happens before paid generation and again when workers execute or async provider
results are finalized. The production NODE-45 adapter reads current NODE-18 Asset/rights facts,
not an analysis-time rights snapshot. For commercial generation, unknown/revoked commercial
rights fail closed. Asset Resolver references additionally require a current explicit APPROVED
usage signal. Durable reference values are storage references, never signed/provider URLs.

## Prompt and hard requirements

The prompt compiler produces stable provider-neutral blocks for objective, content, visual
direction, brand constraints, identity requirements, hard/negative constraints and output
requirements. If a budget cannot afford all requested variants, only the candidate count changes;
exact dimensions and hard identity/constraint requirements are not silently degraded.

## HTTP and worker lifecycle

The public API has three routes:

- `POST /api/v1/projects/{project_id}/image-generations` -> HTTP 202
- `GET /api/v1/image-generations/{generation_id}`
- `POST /api/v1/image-generations/{generation_id}/cancel`

Submit persists the spec/job and publishes work; it does not call the provider. A worker executes
sync providers outside the HTTP request. Async providers persist provider request id plus the
normalized request/result snapshot. Poll uncertainty remains `PROVIDER_PENDING`; the system does
not turn a temporary observation failure into a false terminal failure.

## Output integrity

Provider output references are temporary. Before an image can become a candidate the runtime
checks non-empty/size limits, container signature, structural decode, declared MIME, required
format, exact/minimum dimensions, checksum and PNG alpha when transparency is required. Corrupt
outputs never become READY Artifacts.

A paid result can still be rejected after provider completion; cost projection is recorded before
output validation so this outcome remains auditable.

## Postflight

NODE-46 coordinates rather than reimplements policy engines. Required NODE-39 constraint,
NODE-43 brand or NODE-44 identity validators fail closed when unavailable. Provider safety blocks
become HARD failures. A hard-failed generated Artifact remains DRAFT; a passed candidate is moved
by NODE-42 to READY. NODE-46 never auto-approves an Artifact.

## Artifact and provenance

Each valid candidate becomes its own NODE-42 `RASTER_IMAGE` Artifact with immutable initial
version and original ArtifactFile. Provenance binds generation id, provider/model/request id,
prompt hash/template/ref, reference Asset ids, constraint snapshot, seed, dimensions, routing,
pricing, agent/task/recipe/skills and deployment Git SHA.

Generated output rights are conservative: `AI_GENERATED / PROVIDER_GENERATED_TERMS`, commercial
and redistribution rights unknown, training use false, review status `UNREVIEWED`. Model output
does not imply copyright or commercial safety.

## Persistence

Migration `20260817_0015` follows `20260817_0014` and adds tenant-scoped spec, job, candidate,
pending-provider and cost-projection tables. Database constraints include root operation
uniqueness, variant operation uniqueness, candidate/job tenant relationships, checksums,
non-negative costs and the fixed NODE-27 monetary owner. A tenant-scope trigger protects candidate
writes.

## Validation model

The local deterministic fixture suite validates orchestration/control semantics only. It does not
claim real Chinese text fidelity, product/logo similarity, brand style quality, transparent-edge
quality, provider latency or price accuracy. Those remain a live NODE-23 benchmark gate before
NODE-46 can be COMPLETE.
