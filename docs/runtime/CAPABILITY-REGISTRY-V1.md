# Capability Registry V1

> NODE-23 control-plane contract.  
> Depends on NODE-07 Model Provider Matrix and NODE-22 Model Gateway.

## 1. Responsibility

Capability Registry is the versioned fact/control plane for model selection. Model Gateway remains the execution/data plane.

The Registry answers:

```text
which provider/model exists?
what capability is documented or measured?
what support level and limits apply?
what price snapshot was valid at time T?
what benchmark evidence exists?
which routing profile and organization policy apply?
```

It does not invoke provider APIs and does not store provider credentials.

## 2. Facts are not booleans

Every Capability Claim has:

```text
model_key
capability
support = full | partial | none | unknown
limits
confidence = verified_docs | live_test | inferred
observed_at
source_ref
```

Missing evidence is `unknown`. It is never silently converted to `none` or `full`.

Normal P0 routing accepts only `full`. Callers must explicitly opt into `partial` when a workflow can handle its documented limits.

## 3. Seed provenance

`config/model-registry/registry.seed.v1.yaml` is intentionally JSON syntax, which is a valid YAML 1.2 document. This preserves a stdlib-only loader while meeting the YAML seed contract.

The seed is a compiler manifest rather than a hand-copied second source of provider facts. It points to the versioned NODE-07 artifacts:

```text
docs/models/provider-matrix-manifest.json
docs/models/providers/openai.json
docs/models/providers/google.json
docs/models/providers/anthropic.json
docs/models/providers/black-forest-labs.json
docs/models/providers/runway.json
docs/models/route-candidates.json
evals/datasets/model-provider/suite.json
```

The compiler normalizes those files into an immutable `RegistrySnapshot` and hashes the exact source bytes plus normalized fact identity. NODE-07 currently declares 28 models and all benchmark quality/latency as `NOT_MEASURED`; NODE-23 therefore creates no fake benchmark scores.

## 4. Durable PostgreSQL history

`0010_capability_registry` adds separate tables for:

```text
model_registry_versions
model_registry_models
model_capability_claims
model_pricing_snapshots
model_benchmark_scores
model_routing_profiles
organization_model_policies
```

Registry fact rows are append-only by version. A later RegistryVersion never overwrites older pricing, capability, benchmark, or routing-profile history.

`lumi_app` receives `SELECT` only on these control-plane tables. Seed/activation is performed with migration/admin credentials.

## 5. Pricing semantics

Pricing is not a mutable `current_price` column on Model.

Each PricingSnapshot stores:

```text
price_snapshot_key
model_key
currency
unit
price
minimum_charge
effective_from
valid_until
observed_at
source_ref
```

`RegistrySnapshot.pricing_at(model_key, at_time)` returns the price facts valid at that time. An expired freshness window is not treated as a current price, while the historical row remains available for audit and Cost Ledger provenance.

## 6. Benchmark semantics

BenchmarkScore stores evidence, not a magic provider ranking:

```text
model_key
profile
score
dataset_version
run_id
sample_count
statistics
confidence
observed_at
source_ref
```

Frozen V1 benchmark profiles include:

```text
planning
structured_ir
chinese_copy
image_text_fidelity
product_identity
image_edit_precision
video_motion
```

Different dataset/run versions remain distinct rows. The Registry may select the latest applicable score for routing but historical scores remain queryable.

## 7. Routing profiles

NODE-07 route candidate sets compile into versioned RoutingProfile records. V1 weights are explicit and sum to 1:

```text
quality      0.45
constraint   0.30
cost         0.10
latency      0.10
availability 0.05
```

Candidate ordering from NODE-07 remains a candidate prior until live benchmark evidence exists. `selected_primary=null` in NODE-07 is preserved semantically; NODE-23 does not invent a winner.

## 8. Organization policy

OrganizationModelPolicy is independently versioned and can restrict:

```text
disabled providers
denied models
allowed regions
maximum cost class
preferred models
data-handling restrictions
```

A preference is soft. A disabled provider/model or policy restriction is a hard filter.

## 9. Router integration

`RegistryAwareModelRouter` freezes exactly one `RegistrySnapshot` at the start of each route operation.

It projects registered ProviderAdapters through Registry facts:

```text
adapter = how to call provider
registry = whether/why this model may satisfy the capability
health = whether the route is currently operational
budget = whether the request may spend the estimated amount
```

The existing NODE-22 `ModelRouter` algorithm is reused after Registry projection; provider SDK execution/retry/fallback semantics are not duplicated.

Every accepted RouteCandidate receives reason markers:

```text
REGISTRY_SNAPSHOT:<uuid>
REGISTRY_VERSION:<n>
REGISTRY_HASH:<prefix>
```

These markers flow into NODE-22 routing telemetry/provenance. A hot Registry activation affects new requests only; an already captured snapshot and RoutingDecision stay unchanged.

## 10. Adapter registry is not Capability Registry

`InMemoryProviderRegistry` from NODE-22 remains the runtime collection of installed provider adapters. It must not become the source of capability/pricing/benchmark truth.

Capability Registry is separate and durable. The production composition root injects both:

```text
ProviderRegistry + CapabilityRegistry + HealthRegistry -> RegistryAwareModelRouter
```

This keeps provider SDK/schema details out of Agents/API/Workers while also keeping PostgreSQL ORM details out of Model Gateway.

## 11. Hot reload

`InMemoryCapabilityRegistry` exposes atomic snapshot activation. Version regression is rejected. Reusing a Registry version number with different content hash is rejected.

A control-plane event/watch can compile/load the new version and call `activate(snapshot)`. There is no requirement to restart Agent Runtime or Model Gateway for a new registry snapshot.

## 12. Security

Registry stores no API keys, bearer tokens, provider credentials, or raw provider responses. Runtime role is read-only for registry fact tables.

Source references identify versioned repository evidence or benchmark run references, not secret URLs.

## 13. Acceptance

Contract/unit gate proves:

- all 28 NODE-07 models compile;
- `unknown != none != full`;
- partial capability is filtered unless explicitly allowed;
- expired pricing is not current;
- organization provider deny works;
- benchmark run versions remain distinct;
- cache activation does not mutate captured request snapshot;
- Router uses Registry capability claims and emits snapshot provenance.

PostgreSQL gate proves:

- empty DB upgrades through `0010`;
- ORM/Alembic schema drift is clean;
- seed compiles NODE-07 into DB snapshot;
- 28 models and 15 routing profiles exist;
- NODE-07 `NOT_MEASURED` does not create benchmark rows;
- historical/current pricing query works;
- organization policy is readable;
- `lumi_app` cannot mutate registry facts;
- downgrade/upgrade succeeds.

## 14. Next node

After NODE-23 gates are green: **NODE-24 — Provider Health**.
