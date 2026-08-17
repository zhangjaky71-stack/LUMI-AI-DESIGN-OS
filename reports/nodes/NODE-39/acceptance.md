# NODE-39 Acceptance — Constraint Validator V1

## Status

`IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL`

The current implementation is stacked on `feat/node-38-design-ir-runtime`. Hosted GitHub Actions PASS
is not claimed.

## Delivered

- TypeScript Canvas-facing validator runtime;
- Python Agent/service/export validator runtime;
- portable execution adapter boundary over frozen NODE-14 constraints;
- prospective candidate projection before NODE-38 commit;
- incremental impact analysis with deterministic full-scan fallback;
- twelve P0 validators;
- stable cross-language violation identifiers;
- deterministic health score plus independent `hard_pass`;
- mutation-facet-aware lock enforcement;
- CJK-safe text measurement boundary;
- QR size/quiet-zone/contrast/decode-evidence handling;
- brand token validation;
- identity threshold/unavailable handling;
- full export constraint gate;
- batch aggregation returning all relevant blocking violations;
- safe solver proposal subset;
- explicit NODE-38 second-validation callback for proposed fixes;
- adapter exception fail-closed behavior;
- shared TS/Python violation-id conformance vectors;
- static validator, dedicated CI and five-item production gap ledger.

## Local evidence

The exact NODE-39 candidate source was validated in an isolated scratch workspace.

### Python

```text
PYTHONPATH=apps/api/src pytest -q apps/api/tests/test_constraint_validator_node39.py
16 passed
python -m compileall: PASS
NODE39_CONSTRAINT_VALIDATOR_VALIDATION_PASS
```

The tests cover prospective geometry, lock mutation/facet behavior, CJK measurement unavailable,
QR evidence, identity evidence, brand rules, export dimensions, stable violations, deterministic
health score, incremental-vs-full equivalence, batch aggregation, solver safety, NODE-38 second-pass
callback, adapter failure and randomized geometry boundaries.

### TypeScript

The available local compiler completed an isolated strict compile with repository-equivalent strict
flags:

```text
NODE39_TS_STRICT_COMPILE_PASS
NODE39_TS_RUNTIME_SMOKE_PASS
```

Four violation identity vectors were independently evaluated in TypeScript and Python:

```text
NODE39_TS_PY_VIOLATION_ID_CONFORMANCE_PASS vectors=4
```

Local pnpm 11 / repository TypeScript 6.0.3 / Vitest / Ruff / Pyright PASS are not claimed from the
isolated environment. The hosted workflow owns those release gates.

### Reference benchmark

A 2,001-node synthetic document produced the following non-release reference measurement in the
current container:

```text
incremental prospective validation ~= 11.0 ms
full validation ~= 2.8 ms
incremental nodes scanned = 2
full nodes scanned = 2001
```

The incremental path includes private prospective candidate projection; this measurement is diagnostic,
not a release SLO. Production thresholds require the NODE-08 standard-machine benchmark contract.

## Hosted runner evidence

The first dedicated hosted workflow attempt for PR #106 is run `32011017239`. Its
`constraint-validator` job `95330369896` ended with:

```text
status=completed
conclusion=failure
runner_id=0
runner_name=""
steps=[]
```

No checkout, pnpm install, TypeScript typecheck, Vitest, uv install, Python tests, static validator,
Ruff or Pyright step executed. This is classified as `BLOCKED_EXTERNAL`, consistent with the hosted
runner-allocation failures already observed on preceding nodes. It is not a NODE-39 code or test
failure.

## Correctness and safety assertions

- current/persisted Design IR input is not mutated by validation;
- the operation is projected to a private candidate before prospective checks;
- HARD blocking violations reject commit regardless of health score;
- `LOCK_TEXT` does not accidentally block a move while `LOCK_TRANSFORM` does;
- missing CJK measurement, QR decoder or identity evidence is never treated as PASS;
- adapter exceptions become unavailable evidence instead of silent success;
- batch reports aggregate all relevant blocking violations;
- protected/brand/identity rules are excluded from automatic solver mutation;
- proposed fixes have an explicit NODE-38 apply-preview + second-validation path;
- export validation forces a full constraint scan;
- stable violation ids are deterministic across TS/Python.

## Production qualification

Five production integrations remain deliberately open:

1. real rendered QR raster/decode adapter;
2. rendering-stack-accurate browser/server text shaping adapter;
3. governed identity feature baselines/model versions/thresholds;
4. repository-wide Canvas/Agent/worker/export gate wiring and bypass audit;
5. bounded external-validator execution plus durable telemetry.

See `reports/nodes/NODE-39/gap-ledger.json`.

## Hosted acceptance gate

Before NODE-39 may become COMPLETE, an allocated GitHub runner must execute frozen pnpm install,
TypeScript 6.0.3 typecheck, Vitest, frozen uv install, Python 3.12 tests,
`NODE39_CONSTRAINT_VALIDATOR_VALIDATION_PASS`, gap-ledger parse, Ruff and Pyright.

Next node after acceptance: **NODE-40 — Canvas Renderer V1**.
