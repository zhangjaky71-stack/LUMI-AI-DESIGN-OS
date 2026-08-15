# NODE-09 — Acceptance Evidence

> Status: **BLOCKED_EXTERNAL / VALIDATING**  
> Branch: `feat/node-09-domain-model`  
> Pull Request: `#75`  
> Node: Domain Model  
> Date: 2026-08-16

## Scope implemented

NODE-09 freezes the P0 domain vocabulary before database/API implementation and provides a dependency-free Python executable skeleton under:

```text
apps/api/src/lumi_api/domain/
```

Implemented surfaces:

- application-generated UUIDv7 IDs;
- domain error taxonomy;
- immutable validated value objects;
- Organization, Workspace, Project, Brand, Asset, DesignDocument, Branch, Artifact, ArtifactVersion, AgentRun, Task, Generation and CostEntry entities/aggregates;
- explicit Project, AgentRun, Task, ArtifactVersion and Generation state machines;
- cross-tenant composition rejection;
- Task DAG and Artifact lineage cycle detection;
- append-only CostEntry semantics;
- approved ArtifactVersion immutability;
- storage checksum and ownership invariants;
- OperationIdentity for paid/idempotent Generation side effects;
- repository ports and domain-service ports;
- domain/framework dependency purity test;
- frozen business glossary, context map, ER diagram and NODE-10 translation contract.

## Deterministic local acceptance

Evidence: `reports/nodes/NODE-09/local-domain-test.txt`.

Result in the available validation container:

```text
Python 3.13.5
13 passed in 0.07s
COMPILEALL_PASS
```

Repository CI remains pinned to Python 3.12.*. Local fallback evidence is supplementary and cannot replace repository Ruff/Pyright/Pytest gates.

## Executable contract

`apps/api/tests/test_domain_model.py` validates:

1. UUIDv7 version/variant/time ordering;
2. Decimal Money and currency isolation;
3. Project transitions and terminal state;
4. AgentRun wait/resume/success transitions;
5. Task execution transitions;
6. approved ArtifactVersion immutability;
7. Asset/StorageRef tenant ownership and MimeType validation;
8. cross-tenant relationship rejection;
9. Task DAG cycle rejection;
10. Artifact lineage cycle rejection;
11. immutable CostEntry adjustment/reversal semantics;
12. normalized Generation lifecycle;
13. `organization_id` on every tenant-owned P0 entity;
14. architecture purity scan forbidding framework/provider SDK imports.

The test file contains 13 pytest test functions; several functions assert more than one contract item above.

## Architecture evidence

Canonical documentation:

```text
docs/domain/DOMAIN-MODEL.md
```

The domain package is intentionally free of ORM, HTTP, provider SDK, queue, storage and LangGraph dependencies. Repository and service protocols point outward so NODE-10/NODE-11 adapters depend on the domain rather than redefining it.

## GitHub Actions evidence

PR `#75` head `097f21f89b3dddfdf6e646fc6418ad254b531ed5` triggered:

```text
CI                 31896616875  FAILURE before runner allocation
Secret Scan        31896616861  FAILURE before runner allocation
Dependency Review  31896616864  FAILURE before useful execution
CodeQL             31896616880  SKIPPED
```

Repository CI job `changes` (`95040793392`) completed in roughly three seconds with:

```text
runner_id = 0
steps = []
```

GitHub annotation:

```text
The job was not started because recent account payments have failed
or your spending limit needs to be increased. Please check the
'Billing & plans' section in your settings.
```

This is the same account-level platform condition independently observed by NODE-08, but this report records NODE-09's own run/job evidence. It is classified under `docs/IMPLEMENTATION-PROTOCOL.md` as `BLOCKED_EXTERNAL`, not as a domain code/test failure.

Required recovery after GitHub billing/spending-limit access is restored:

1. re-run PR `#75` checks;
2. require repository Python Ruff/Pyright/Pytest under Python 3.12.* green;
3. require contracts/integration/security gates green;
4. address any real code failure rather than bypassing a gate;
5. only then merge PR #75, update `docs/NODE-INDEX.md`, and mark NODE-09 `COMPLETE`.

## Acceptance checklist

- [x] All P0 business objects have explicit responsibilities.
- [x] Asset / Artifact / DesignDocument / ArtifactVersion are distinct roles.
- [x] LangGraph state and domain state are explicitly separated.
- [x] State machines and key invariants have executable tests.
- [x] `organization_id` is structurally required on every tenant-owned P0 entity.
- [x] Domain package contains no ORM/HTTP/provider/LangGraph implementation dependency.
- [x] Local deterministic domain tests pass: 13/13.
- [x] Local compileall passes.
- [ ] Repository Ruff format/lint passes — `BLOCKED_EXTERNAL`.
- [ ] Repository Pyright passes — `BLOCKED_EXTERNAL`.
- [ ] Repository Pytest passes under Python 3.12.* — `BLOCKED_EXTERNAL`.
- [ ] Repository contract/integration/security gates pass — `BLOCKED_EXTERNAL`.
- [ ] Pull request merged and NODE index updated.

NODE-09 is implemented but remains **`BLOCKED_EXTERNAL / VALIDATING`**, not `COMPLETE`.
