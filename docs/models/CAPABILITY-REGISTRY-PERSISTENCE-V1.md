# Capability Registry Persistence Mapping V1

Status: **NODE-23 IMPLEMENTATION CONTRACT**

## Table map

| Domain entity | PostgreSQL table | Scope | Runtime mutation |
|---|---|---|---|
| Registry Version | `model_registry_versions` | global | SELECT only |
| Provider | `model_providers` | global | SELECT only |
| Model Definition | `model_definitions` | global | SELECT only |
| Model Revision | `model_revisions` | global/versioned | SELECT only |
| Capability Definition | `model_capabilities` | global | SELECT only |
| Capability Claim | `model_capability_claims` | global/versioned | SELECT only |
| Pricing Snapshot | `model_pricing_snapshots` | global/versioned | SELECT only |
| Benchmark Score | `model_benchmark_scores` | global/versioned | SELECT only |
| Routing Profile | `model_routing_profiles` | global/versioned | SELECT only |
| Profile Candidate | `model_routing_profile_candidates` | global/versioned | SELECT only |
| Organization Model Policy | `organization_model_policies` | tenant | SELECT/INSERT/UPDATE under RLS |

## Version identity

`model_registry_versions.version` and `checksum_sha256` are unique. The deterministic seed
publisher first reads an existing version. If the same semantic version already exists with a
different checksum it raises `REGISTRY_VERSION_CHECKSUM_CONFLICT`; it never overwrites the
published snapshot.

Stable UUIDv5 identities are used for seed publication so replaying the exact same source is
idempotent. A new source snapshot must receive a new registry version.

## Definition versus revision

`model_definitions` owns stable provider/model identity. `model_revisions` records the state of
that model inside a registry version: lifecycle, route eligibility, regions, observed time,
source references and provider metadata. This prevents model lifecycle changes from rewriting
old provenance.

## Capability claims

Claims are unique per model revision + capability. `support` is constrained to
`full|partial|none|unknown`; confidence is constrained to
`verified_docs|live_test|inferred`. Source and observed time are required.

## Pricing

Pricing rows are immutable evidence attached to a registry version and model revision. Metric
and unit remain explicit; NODE-23 does not force token, image and video billing into one fake
unit. Amount and optional minimum charge are non-negative USD numeric values. Effective,
observed and optional expiry times are persisted.

The domain read API defaults to non-expired prices for live routing and can explicitly include
expired records for historical Cost Ledger explanation.

## Benchmark scores

A row requires dataset version, run ID, positive sample count, score 0..100, source and observed
time. Confidence intervals must be supplied as a complete pair and contain the point estimate.
Statistics are retained as structured JSON. NODE-07 `NOT_MEASURED` produces zero rows.

## Routing profiles

Profiles are scoped to a registry version. Required capabilities and exact weights are retained.
Candidates have an ordinal so the original NODE-07 candidate set order remains inspectable.
Stable fallback membership is explicit rather than inferred from model naming.

## Tenant policy

`organization_model_policies.organization_id` is both the primary key and organization FK. RLS
uses `lumi_current_organization_id()`. Policy version must be positive and callers are expected
to increase it monotonically. Runtime DELETE is revoked to avoid erasing policy history through
ordinary application credentials.

## Runtime grants

If role `lumi_app` exists, migration 0007 grants it SELECT on all global registry tables and
revokes INSERT/UPDATE/DELETE. Registry publication therefore requires the migration/admin role.
Tenant policy receives SELECT/INSERT/UPDATE only under RLS.

## Seed and round trip

`tools/node23/seed_capability_registry.py`:

1. loads NODE-07 sources through the same domain normalizer used by tests;
2. checks version/checksum immutability;
3. inserts capability definitions;
4. inserts providers, stable definitions and versioned revisions;
5. inserts claims, all normalized prices and any real benchmark rows;
6. inserts routing profiles/candidate order;
7. returns cardinality evidence.

`tools/node23/test_registry_database.py` repeats the publisher to prove idempotency, reconciles
raw versus normalized pricing count, loads the snapshot back through
`PostgresCapabilityRegistryStore`, verifies checksum/cardinality stability, checks policy RLS and
runtime read-only grants, and injects a checksum conflict to prove fail-closed behavior.

## Migration rollback

`20260816_0007` is forward-only from NODE-20's `0006` baseline and does not rewrite earlier
migration files. Downgrade removes the organization policy first and then all registry tables in
foreign-key-safe reverse order. The dedicated workflow must verify that the NODE-20 baseline
remains present after downgrade, then reapply 0007 and rerun registry invariants.
