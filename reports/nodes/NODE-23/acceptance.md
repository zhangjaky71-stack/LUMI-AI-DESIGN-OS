# NODE-23 Acceptance — Capability Registry

Status: **IMPLEMENTED / VALIDATING**

## Delivered

- [x] Registry seed compiler manifest sourced from NODE-07 artifacts.
- [x] Immutable RegistrySnapshot contract.
- [x] Provider / Model Snapshot facts.
- [x] CapabilityClaim with full/partial/none/unknown.
- [x] verified_docs/live_test/inferred evidence confidence.
- [x] observed_at + source_ref on capability/pricing/benchmark/routing facts.
- [x] historical PricingSnapshot query.
- [x] BenchmarkScore with dataset/run/sample/statistics identity.
- [x] RoutingProfile with explicit normalized weights.
- [x] versioned OrganizationModelPolicy.
- [x] hot snapshot activation with version/content conflict guards.
- [x] Registry-aware NODE-22 Router adapter.
- [x] per-request snapshot provenance markers.
- [x] PostgreSQL `0010_capability_registry` migration.
- [x] separate DB tables for model/capability/pricing/benchmark/routing/policy.
- [x] runtime `lumi_app` read-only registry privileges.
- [x] deterministic DB seed from compiled NODE-07 source.
- [x] static contract gate.
- [x] unit tests for unknown/partial/pricing/policy/benchmark/cache/router semantics.
- [x] PostgreSQL seed/integration/migration workflow authored.

## Evidence discipline

NODE-07 currently marks all 28 model benchmark quality/latency values `NOT_MEASURED`. NODE-23 therefore intentionally seeds **zero** BenchmarkScore rows. No model quality winner is fabricated.

The committed `.yaml` seed uses JSON syntax, valid under YAML 1.2, so the runtime remains stdlib-only and does not add PyYAML or alter `uv.lock`.

## Required green evidence before COMPLETE

- [ ] Registry contract compile PASS.
- [ ] static Registry validator PASS.
- [ ] capability registry unit tests PASS.
- [ ] frozen `uv sync --all-packages --frozen` PASS.
- [ ] targeted Ruff PASS.
- [ ] targeted Pyright PASS.
- [ ] empty DB -> Alembic `0010` PASS.
- [ ] ORM/Alembic drift PASS.
- [ ] deterministic Project seed PASS.
- [ ] NODE-07 registry seed -> DB PASS.
- [ ] PostgreSQL Registry acceptance PASS.
- [ ] runtime mutation-denial PASS.
- [ ] migration downgrade/upgrade PASS.
- [ ] upstream NODE-22/NODE-21 required gates remain consistent.

NODE-23 is not COMPLETE until hosted gates actually execute. If the existing GitHub Actions billing/spending blocker persists, record the exact runner evidence here rather than reporting a code test failure.

Next node: **NODE-24 — Provider Health**.
