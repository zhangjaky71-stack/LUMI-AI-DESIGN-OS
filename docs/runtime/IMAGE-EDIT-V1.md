# Image Edit Runtime V1 — NODE-47

## Purpose

NODE-47 is the product-grade image editing boundary for LUMI AI Design OS. It chooses the
smallest safe edit surface, preserves protected content, records immutable lineage, and only
invokes a paid image-edit provider when the requested change cannot be expressed as a Design IR
operation.

## Frozen routing model

The runtime exposes five routes:

1. `STRUCTURAL_IR_EDIT` — text, position, size, font, color, layer order, reparent, background
   property, or explicit asset replacement that Design IR can perform deterministically.
2. `PIXEL_LOCAL_EDIT` — masked local pixel edit.
3. `REGENERATE_REGION` — bounded region regeneration/outpaint.
4. `FULL_IMAGE_EDIT` — broad pixel edit only after explicit user confirmation where required.
5. `HYBRID` — safe composite/mask path when a broad provider edit is not acceptable.

Structural-first is a hard invariant: if a supported Design IR operation can satisfy the intent,
NODE-47 must not invoke Model Gateway.

## Immutable source contract

Every edit binds the exact tenant/project, source Asset id/version/checksum, source Artifact id and
ArtifactVersion id, dimensions, MIME type, rights assertion, and durable storage ref. Source access
is re-authorized at submit, worker execution, and async completion. Asset version, ArtifactVersion,
checksum, and dimensions must still match the submitted snapshot.

The source ArtifactVersion is never overwritten. Pixel outcomes append a new ArtifactVersion; a
PASS advances the source branch with NODE-42 compare-and-swap, while REPAIR/REJECT candidates live
on a forked review branch so the main head is not corrupted.

## Mask and approval lifecycle

Mask coordinates are source-pixel coordinates. User brush, Design IR, detector, and agent-proposed
masks all carry source hash/version/dimensions plus a mask checksum and durable ref. HARD protected
regions cannot overlap the editable mask.

High-impact agent masks enter `AWAITING_MASK_APPROVAL`. Broad edits that touch protected content
enter `AWAITING_CONFIRMATION`. Approval actors come from the authenticated request context; client
payloads cannot self-assert approval. Approval state is excluded from creative semantic hashing so
an approval does not create a false paid-operation semantic conflict.

## Model Gateway contract

NODE-47 builds a provider-neutral request and delegates provider payload translation, retries,
paid-side-effect idempotency, health/fallback, budget reservation, and NODE-27 settlement to
NODE-22 Model Gateway.

For a HARD local edit, Model Router must select the exact model only when it supports both the
primary capability (`image.mask_edit`) and every additional required capability such as
`image.reference_consistency`. Provider-level support on a different model is not sufficient.

## Postflight and fail-closed behavior

Before a candidate can PASS, NODE-47 can require:

- protected-region visual preservation;
- NODE-39 constraint validation;
- NODE-43 Brand Rules validation;
- NODE-44 Identity validation;
- QR payload decode;
- locked text/logo OCR;
- intended-region change evidence;
- exact output dimensions;
- Model Gateway safety outcome.

A required validator that is unavailable produces an `UNAVAILABLE` HARD finding. Provider safety
`blocked=true`, `content_filter`, or `safety_block` is a HARD rejection. Protected-pixel compositing
may repair visual preservation failures, but it can never erase a provider safety rejection.

## Canvas/Design IR handoff

Only a PASS candidate may update the active design. The candidate is first materialized as a durable
Asset/ArtifactVersion. NODE-47 then applies Design IR `REPLACE_ASSET` using the new `asset_id` under
DesignDocument version compare-and-swap. The resulting document version records the source Artifact
link for audit/lineage.

## Provenance

The immutable edit provenance snapshot contains route, source ArtifactVersion/checksum, instruction
hash, mask hash, protected-region hash, constraint snapshot hash, provider/model/revision/registry
snapshot/request id, routing reasons, pricing/cost projection, seed, AgentRun, agent version,
recipe/skill versions, code git SHA, safety metadata, finish reason, validation decision, and
identity validation snapshot.

The NODE-47 cost projection is audit-only. NODE-27 Model Gateway settlement remains the sole
monetary owner.

## Production completion gate

Synthetic tests and the 125-case control-plane corpus prove orchestration behavior, not production
visual quality. NODE-47 is not COMPLETE until the five gaps in `reports/nodes/NODE-47/gap-ledger.json`
are closed, including live provider A-E goldens and live PostgreSQL/Artifact/Design IR concurrency
acceptance.
