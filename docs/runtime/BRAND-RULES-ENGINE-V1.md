# Brand Rules Engine V1

## Purpose

NODE-43 turns brand consistency into versioned, machine-readable project truth.
Prompt prose is not the source of truth. Published `BrandRuleSet` snapshots are.

## Runtime model

```text
Brand Kit editing resources (existing mutable tables)
  brands / brand_palettes / brand_fonts / brand_logos / brand_rules
                         |
                         v
              BrandRuleSet draft
                         |
       +-----------------+-----------------+
       |                                   |
manual/user rules                 guide extraction proposal
       |                                   |
       |                              cited evidence
       |                                   |
       |                             human review
       |                                   |
       +------------------+----------------+
                          v
              immutable published snapshot
                          |
          +---------------+---------------+
          |               |               |
     BrandContext    Compliance      NODE-14 ConstraintSet
          |               |               |
     Context Engine   approval gate   NODE-39 validator
```

## Canonical contracts

`lumi_api.brand_rules.contracts` defines:

- `BrandTokenSet`
- `BrandAssetSet`
- `BrandRule`
- `BrandRuleSet`
- `BrandVoice`
- `BrandVisualStyle`
- `BrandGuideProposal`
- `GuideCitation`
- `BrandContext`
- `BrandObservation`
- `BrandViolation`
- `ComplianceResult`

Rule severity is exactly `HARD | SOFT | ADVISORY`, matching NODE-14.
Rule sources are:

- `USER_EXPLICIT`
- `APPROVED_GUIDE_EXTRACTION`
- `MANUAL_ADMIN`
- `INFERRED_PROPOSAL`

`INFERRED_PROPOSAL` is never directly publishable.

## Publication and immutability

A rule-set version has an immutable `snapshot_hash`.
The following fields are snapshot content and cannot change after insert:

- tenant / brand identity
- version number
- source
- token set
- asset set
- rules
- voice
- visual style
- source proposal
- creator / creation time

Only lifecycle metadata can transition from draft to published:
`status`, `published_at`, `published_by`.

After `PUBLISHED` or `RETIRED`, lifecycle state is terminal in V1.

PostgreSQL independently enforces snapshot immutability through
`trg_brand_rule_set_snapshot_immutable`.

## Concurrency-safe version allocation

`brand_rule_version_counters` reserves a per-brand version number with an
atomic PostgreSQL `INSERT .. ON CONFLICT .. DO UPDATE .. RETURNING`.
Concurrent publishers cannot silently receive the same version.

Version numbers may contain gaps after a failed transaction. Identity is the
immutable rule-set UUID plus version number and snapshot hash; contiguous
numbering is not a correctness requirement.

## Guide extraction trust boundary

```text
Brand guide Asset
  -> Knowledge / parser extraction
  -> Brand Agent structured INFERRED_PROPOSAL
  -> page-level GuideCitation[]
  -> human review
  -> APPROVED_GUIDE_EXTRACTION
  -> publish immutable BrandRuleSet
```

The runtime requires at least one citation and requires every citation to
reference the proposal's source Asset. A proposal cannot be published before
an authenticated human review. Review identity comes from the API
`RequestContext.actor_id`, not from client-supplied actor text.

The production PDF/knowledge extraction worker remains a separate adapter; the
runtime does not pretend an LLM inference is approved policy.

## Brand Context

`BrandContext` is deliberately compact:

- exact `rule_set_id`
- exact `rule_set_version`
- exact `snapshot_hash`
- HARD rules
- selected tokens
- allowed logo/font Asset IDs
- voice summary
- reference Asset IDs

`BrandContextRetrievalSource` injects this into NODE-34 as
`TRUSTED_PROJECT_DATA`, `ContextKind.BRAND_RULE`, `required=True`,
`pinned=True`, with the exact version/hash in `ContextSourceRef`.

## Compliance

Deterministic V1 checks include:

- required/allowed token binding
- allowed and forbidden color
- minimum contrast
- allowed font
- font Asset availability and rights
- minimum font size
- allowed logo Asset
- logo minimum size
- logo clear space
- logo rotation/stretch/recolor

`HARD` violations make `can_approve=False`. SOFT/ADVISORY violations affect
score but do not become hard blockers.

Voice and broad visual style remain structured context in V1. Provider-backed
semantic/VLM grading is an explicit production gap and is not silently treated
as a deterministic pass.

## NODE-14 / NODE-39 bridge

`compile_brand_constraints()` emits canonical NODE-14 `ConstraintSet` values
with:

```text
source = APPROVED_BRAND_RULE
severity = HARD | SOFT | ADVISORY
priority = 500
```

Known deterministic rules are translated to NODE-39 parameters:

- `MIN_CONTRAST` -> `REQUIRE_CONTRAST.min_ratio`
- `FONT_MIN_SIZE` -> `REQUIRE_TEXT_READABILITY.min_font_size`
- `ALLOWED_COLOR` -> `REQUIRE_BRAND_COMPLIANCE.allowed_colors`
- `FONT_ALLOWED` -> `REQUIRE_BRAND_COMPLIANCE.allowed_fonts`
- `LOGO_TRANSFORM` -> `LOCK_BRAND.logo_rotation_forbidden`

The canonical constraint ID reuses the UUIDv7 BrandRule ID, preserving stable
traceability from violation back to brand rule.

The adapter intentionally uses an unscoped `ConstraintScope()` unless a real
Design IR node scope is known. It does not invent semantic tags that would
accidentally match zero nodes.

## Asset rights

Publication validates every allowed font Asset through an `AssetRightsReader`.
The PostgreSQL implementation reads NODE-18 `assets + asset_rights` and
requires:

- same tenant
- Asset exists
- Asset status is `ready`
- media kind is `font`
- `commercial_use` is not explicitly denied

Unavailable rights are not treated as pass.

## Exact historical rule-set capture

Migration `20260817_0012` adds:

- `brands.active_rule_set_version_id`
- `artifact_versions.brand_rule_set_version_id`
- `agent_runs.brand_rule_set_version_id`

Database triggers capture the currently active published rule-set version at
`ArtifactVersion` and `AgentRun` INSERT time. Brand changes therefore do not
retroactively mutate prior run/artifact interpretation.

A validation trigger prevents a Brand from pointing at a rule-set belonging to
another tenant/brand or at a non-published rule-set.

## API

Authenticated routes:

```text
POST /api/v1/brands/{brand_id}/rule-sets
POST /api/v1/brands/{brand_id}/rule-sets/{rule_set_id}/publish
GET  /api/v1/brands/{brand_id}/context
POST /api/v1/brands/{brand_id}/compliance
POST /api/v1/brands/{brand_id}/guide-proposals
POST /api/v1/brands/{brand_id}/guide-proposals/{proposal_id}/review
POST /api/v1/brands/{brand_id}/guide-proposals/{proposal_id}/publish
```

Writes use the existing NODE-16 auth guard and OrganizationId contract.
Review/publish actor identity is taken from authenticated request context.

## Evaluation

Deterministic fixtures live at:

`evals/node43/brand-rule-fixtures.json`

The evaluator:

`tools/node43/run_brand_rule_eval.py`

covers 25 pass/fail cases across color, contrast, typography, token binding,
logo asset, size, clear-space and transform rules.

## Operational qualification

NODE-43 is not considered production complete until the remaining gaps in
`reports/nodes/NODE-43/gap-ledger.json` have real-service evidence.
