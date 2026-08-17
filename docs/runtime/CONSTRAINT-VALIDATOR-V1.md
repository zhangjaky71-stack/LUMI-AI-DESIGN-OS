# LUMI Constraint Validator V1

## Purpose

NODE-39 turns the NODE-14 Constraint contract into an executable validation gate for the NODE-38
Design IR Runtime. The validator is deliberately separate from the solver:

```text
operation intent
-> prospective candidate projection
-> impact analysis
-> deterministic validators
-> stable violations / health score
-> NODE-38 commit only when HARD passes
```

A solver may propose operations, but it never mutates a persisted Design IR document by itself.

## Runtime boundaries

The implementation has two deterministic surfaces:

- TypeScript: `packages/design-constraints/src/validator/` for Canvas/local preflight.
- Python: `apps/api/src/lumi_api/constraint_validator/` for Agent/service/export validation.

The portable `RuntimeConstraint` is an execution view of the frozen NODE-14 rule. The Python
`node14_adapter.py` maps the canonical NODE-14 Pydantic `Constraint` into that execution view without
changing NODE-14's public contract.

## NODE-38 integration

NODE-38 invokes preflight before applying an operation. Therefore NODE-39 must validate the
**prospective** state, not merely the current document. `projectOperation/project_operation` creates a
private candidate view for supported Design Operations. The candidate is never committed by the
validator.

TypeScript `createIrPreflight()` returns a function structurally compatible with NODE-38's
`ConstraintPreflight`:

```text
(document, operation) -> IR_CONSTRAINT_FAILED[]
```

The pure batch gate validates all child operations and returns all relevant violations. NODE-38 may
still fail fast on the first blocking issue inside its transaction; callers that need a complete batch
error panel should run `validateBatch()` before invoking the commit path.

## P0 validators

The frozen V1 registry has exactly twelve validators:

1. BoundsValidator
2. SafeAreaValidator
3. LockedRegionValidator
4. TextOverflowValidator
5. FontSizeValidator
6. AspectRatioValidator
7. ContrastValidator
8. ProtectedRegionValidator
9. QRValidator
10. BrandTokenValidator
11. IdentityPreservationValidator
12. ExportDimensionValidator

### Lock facets

Lock rules are mutation-specific. `LOCK_TEXT` blocks `SET_TEXT` but does not block `MOVE_NODE`;
`LOCK_TRANSFORM` blocks move/resize/rotate; other lock types map to their matching operation facets.
This avoids turning every lock into a global node freeze.

### Text

The validator never estimates Chinese/CJK text width with Latin average-character heuristics. Exact
text overflow uses a `text_measure` adapter. If the adapter is absent or fails and exact measurement is
required, the violation is `VALIDATION_UNAVAILABLE`; HARD rules fail closed. Font size, forbidden font,
max-line and line-height-range rules are deterministic once the measurements/properties exist.

### QR

The deterministic core validates effective output size, quiet zone and contrast. Actual raster decode
is an adapter boundary. Missing/failed decode evidence is not treated as PASS. For a HARD QR rule it
blocks until real evidence or a policy-approved human path is available.

### Brand and identity

Brand token validation covers approved colors/fonts and forbidden logo rotation in V1. Identity
preservation uses an explicit score adapter. Missing identity baselines or adapter failures yield
unavailable violations rather than optimistic success.

## Incremental validation

The impact analyzer starts from operation targets, expands parent/children and constraint-scoped
nodes, then compares the impact size with a deterministic threshold. It falls back to a full scan when
that threshold is exceeded. The report exposes:

- validators_run
- nodes_scanned
- violations_count
- blocking_count
- fallback_full_scan

Wall-clock duration is intentionally not part of the pure deterministic report. Production telemetry
may measure duration around the pure function without changing its result.

## Violation identity

Violations use a stable `cv1-*` FNV-1a 64-bit identifier over canonical UTF-8 data containing:

- constraint id
- validator id
- sorted affected node ids
- message code

The identifier is a UI/audit de-duplication key, not a security digest. Four shared TS/Python vectors
freeze cross-language behavior.

## Health score

Health score is deterministic weighted compliance:

```text
HARD = 5
SOFT = 2
ADVISORY = 1
```

A rule contributes its weight once even if it emits multiple violations. `hard_pass` remains an
independent invariant. A perfect average can never override a HARD blocking violation.

## Validator failure policy

External adapters are not trusted to always be available. Missing or raised adapter failures become
explicit unavailable violations. Under the default policy:

```text
HARD unavailable -> blocking
SOFT/ADVISORY unavailable -> non-blocking warning/unavailable report
```

No timeout/error is silently converted into PASS.

## Auto-fix

The solver only proposes a safe subset:

- move back toward allowed bounds/safe area
- raise minimum font size
- restore aspect ratio

It never auto-fixes protected-region, brand-token or identity-preservation violations. The preferred
production path is `validateProposedFixWithIrRuntime`: apply the proposal through a NODE-38 preview
adapter first, then run a second full constraint validation. Only the caller/approval layer may commit.

## Export gate

`validateExport()` always forces a full constraint scan and enables ExportDimensionValidator. Export
workers must pair it with NODE-38 structural validation before rendering. No export path is allowed to
skip either gate.

## Production gaps

The deterministic runtime does not pretend the following production integrations already exist:

1. real rendered QR decoder adapter;
2. production text shaping/measurement adapter;
3. governed identity feature baseline and thresholds;
4. repository-wide Canvas/Agent/worker/export wiring and bypass audit;
5. bounded external-validator execution plus durable telemetry.

See `reports/nodes/NODE-39/gap-ledger.json`.
