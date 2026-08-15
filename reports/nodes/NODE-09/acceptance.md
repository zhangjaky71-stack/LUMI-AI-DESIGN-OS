# NODE-09 — Acceptance Evidence

> Status: VALIDATING  
> Branch: `feat/node-09-domain-model`  
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

Repository CI remains pinned to Python 3.12.*. Local fallback evidence is therefore supplementary and cannot replace the repository Ruff/Pyright/Pytest gates.

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

## CI evidence

Pending the first NODE-09 pull-request run.

The repository currently has an account-level GitHub Actions billing/spending-limit block observed on PR #74. NODE-09 will record its own workflow result after its PR is opened. A pre-runner billing failure will be classified `BLOCKED_EXTERNAL` rather than a code failure, but NODE-09 will not be marked COMPLETE until the actual Python/front-end/contracts/integration/security gates can run successfully.

## Acceptance checklist

- [x] All P0 business objects have explicit responsibilities.
- [x] Asset / Artifact / DesignDocument / ArtifactVersion are distinct roles.
- [x] LangGraph state and domain state are explicitly separated.
- [x] State machines and key invariants have executable tests.
- [x] `organization_id` is structurally required on every tenant-owned P0 entity.
- [x] Domain package contains no ORM/HTTP/provider/LangGraph implementation dependency.
- [x] Local deterministic domain tests pass: 13/13.
- [x] Local compileall passes.
- [ ] Repository Ruff format/lint passes.
- [ ] Repository Pyright passes.
- [ ] Repository Pytest passes under Python 3.12.*.
- [ ] Repository contract/integration/security gates pass.
- [ ] Pull request merged and NODE index updated.

NODE-09 remains `VALIDATING`, not `COMPLETE`, until repository-hosted validation is green.
