# Capability Registry V1

Status: **FROZEN FOR NODE-23 IMPLEMENTATION**  
Owner: AI Infrastructure  
Depends on: NODE-07 Model Provider Matrix, NODE-22 Model Gateway

## 1. Purpose

Capability Registry is the control-plane source of truth for model routing facts. Provider
adapters execute requests; they are not allowed to define the production model catalog by
hard-coded `adapter.models()` lists.

The registry separates facts that change at different cadences:

- Provider identity;
- stable Model Definition identity;
- versioned Model Revision/Snapshot;
- Capability Claims and their evidence;
- historical Pricing Snapshots;
- versioned Benchmark Scores;
- Routing Profiles and candidate sets;
- tenant-scoped Organization Model Policy.

A request captures one immutable `RegistrySnapshot` at route start. Publishing a new version
changes future requests only; in-flight requests retain the original snapshot ID and model
revision provenance.

## 2. Seed truth

P0 source material is the completed NODE-07 research set:

- `config/model-registry.seed.json`;
- `docs/models/providers/*.json`;
- `docs/models/route-candidates.json`.

NODE-23 normalizes that material; it does not re-label marketing copy as benchmark evidence.
The current seed preserves exactly five providers, 28 model records and 15 route profiles.
`benchmark_status=NOT_MEASURED` produces no `BenchmarkScore` row.

Provider-native pricing shapes are retained as distinct pricing snapshots. Both fields such as
`usd_per_million` and native records such as `usd` per video-second are normalized without
silently dropping records. Static and PostgreSQL gates reconcile raw pricing record count with
normalized snapshot count.

## 3. Capability Claim

Each claim contains:

```text
model_key
capability
support = full | partial | none | unknown
limits
confidence = verified_docs | live_test | inferred
observed_at
source_ref
```

`unknown` is neither false nor full. Default routing accepts `full` only. `partial` requires an
explicit request opt-in and still retains its partial provenance. `unknown` and `none` are never
route eligible.

Derived claims are conservative. For example, an OCR-like route inferred from a multimodal role
is `partial + inferred`; it is not promoted to verified full OCR support.

## 4. Lifecycle

Model lifecycle is one of:

- `stable`;
- `preview`;
- `deprecated`;
- `legacy`;
- `shutdown`.

Deprecated, legacy and shutdown revisions cannot be route eligible. Preview models may remain
candidate facts but must not silently become the sole strict production primary when the
source route requires a stable fallback.

## 5. Pricing history

Pricing is immutable historical evidence, not a mutable field on Model Definition.

A Pricing Snapshot records provider/model revision, metric, currency, unit, amount, optional
minimum charge/region, effective time, observation time, optional expiry and source reference.
The live query excludes expired snapshots by default. Historical queries can intentionally
request stale/expired records so old Cost Ledger entries remain explainable.

Publishing a price update therefore means publishing a new registry version/snapshot rather
than overwriting the old price.

## 6. Benchmark evidence

A `BenchmarkScore` is valid only with:

- benchmark profile;
- dataset version;
- run ID;
- sample count;
- observed time and source;
- point score;
- optional complete confidence interval;
- statistics payload.

NODE-23 never turns `NOT_MEASURED` into a numeric score. Future benchmark runs may coexist for
the same model/profile; latest selection is evidence-version aware.

Expected benchmark dimensions include planning, structured IR, Chinese copy, image text
fidelity, product identity, edit precision and video motion.

## 7. Routing Profiles

Routing Profiles contain required capabilities, candidate model keys, stable fallback keys,
selection gate, optional minimum quality and five versioned weights:

```text
quality
constraint
cost
latency
availability
```

Weights must be non-negative and sum exactly to 1.00.

`RoutingProfileEvaluator` is evidence-aware. A candidate with incomplete required evidence gets
`score=None` plus `insufficient_evidence`; candidate order may be preserved for inspection, but
no winner is invented. Only complete evidence yields a weighted score.

NODE-07 `selected_primary=null` is therefore preserved until real benchmark/health/cost evidence
exists.

## 8. Organization Model Policy

Tenant policy can declare:

- disabled providers;
- allowed regions;
- preferred models;
- max cost class;
- data-handling restrictions;
- monotonically increasing policy version.

Policy filtering occurs before preference bonuses. An organization-blocked provider cannot be
re-enabled by a user preference hint. PostgreSQL stores this table under organization RLS.

## 9. Router integration

`ProviderRegistry` now means execution transport registry. `CapabilityRegistry` means catalog
truth. `ModelRouter` captures a Capability Registry snapshot, lists eligible models through that
snapshot and then asks ProviderRegistry whether a transport adapter exists.

A catalog model without an execution adapter is rejected as `adapter_unavailable`; the model
fact remains in the catalog rather than being deleted or falsely called executable.

Registry-backed `ProviderModel` values carry:

- `registry_snapshot_id`;
- `model_revision_id`;
- explicit `quality_measured` and `latency_measured` flags.

When NODE-07 has no live measurements, Router records `quality_not_measured` and
`latency_not_measured`; it does not treat the compatibility default score as benchmark truth.

ProviderRegistry is bound to the Capability Registry for model resolution, so async
`get_async_status`/`cancel` can resolve a catalog model after worker/process restart instead of
requiring it to exist in an adapter-local hard-coded list.

## 10. Cache and hot reload

`CapabilityRegistry.capture_snapshot()` returns the immutable current snapshot. `publish()` swaps
the current pointer only when a new snapshot identity arrives. Reusing the same snapshot ID with
a different checksum fails closed.

`PostgresCapabilityRegistryStore.refresh()` loads the latest published DB snapshot and publishes
it only when the identity changes. Existing captured objects remain unchanged.

NODE-12 v1 does not contain a registry-version event, so multi-process broker invalidation is an
explicit follow-up rather than an unversioned event added behind the frozen protocol.

## 11. PostgreSQL source of truth

Migration `20260816_0007` creates normalized global control-plane tables plus one tenant table.
The deterministic publisher uses stable UUIDs and rejects same-version/different-checksum
publication.

Runtime role `lumi_app` receives SELECT only on global Registry fact tables. It may SELECT,
INSERT and UPDATE tenant-scoped organization policy under RLS, but not DELETE it. Registry
publishing is therefore an administrative/migration-owner action rather than an ordinary app
write.

`PostgresCapabilityRegistryStore` reconstructs the same domain snapshot from persisted rows and
can load tenant policy inside an organization-scoped transaction.

## 12. Startup/readiness behavior

Registry truth and execution readiness are separate. A provider/model can be documented in the
catalog while unavailable to the current deployment because its adapter, credential or health
binding is absent.

NODE-23 fails such execution candidates closed. Google, Black Forest Labs and Runway facts from
NODE-07 are retained, but their execution adapters are an explicit gap rather than a reason to
remove their records.

## 13. Security and provenance

The Registry stores no provider API secrets. Capability evidence requires source and observed
time. Pricing requires source and effective/observed time. Benchmark evidence requires source,
run and dataset identity. Route decisions retain snapshot identity.

Tenant policy cannot mutate global facts. Application runtime cannot rewrite published pricing
or benchmark history.

## 14. Explicit non-claims

NODE-23 does not claim:

- all five providers have executable adapters;
- live LUMI benchmark winners exist;
- NODE-24 health persistence is complete;
- NODE-27 immutable Cost Ledger/budget reservation is complete;
- broker-wide registry invalidation is wired into frozen NODE-12 v1;
- admin publish approval UI/API is complete;
- asyncpg is a reviewed frozen Model Gateway production dependency;
- NODE-22 standalone `lumi-api -> lumi-model-gateway` packaging gap is closed;
- Hosted Actions passed when GitHub assigned no runner.

Next: **NODE-24 — Provider Health**.
