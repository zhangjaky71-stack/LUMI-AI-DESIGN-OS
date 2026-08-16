# NODE-25 Acceptance — Tool Gateway

Status: **IMPLEMENTED / VALIDATING**

## Delivered

- [x] provider-neutral ToolDefinition / ToolRequest / ToolResult contracts.
- [x] versioned Tool Registry with exact and `major.x` resolution.
- [x] risk tiers for read/write/destructive/financial/privileged tools.
- [x] write-class definitions require idempotency at construction time.
- [x] default-deny Agent tool allowlist.
- [x] Organization allow/deny narrowing.
- [x] explicit root-vs-subagent parent-scope semantics.
- [x] subagent permission non-escalation.
- [x] input schema validation before approval/execution.
- [x] output schema validation before Agent return/offload.
- [x] HITL contract for external/destructive/financial/privileged risks.
- [x] approval cannot be inferred from token presence alone.
- [x] SideEffectGuard port for NODE-20 idempotency/reconciliation.
- [x] write calls require idempotency key + SideEffectGuard.
- [x] duplicate write replay contract with one adapter invocation.
- [x] bounded adapter timeout and normalized errors.
- [x] large structured output offload with bounded inline preview.
- [x] structured Audit with recursive secret-field redaction.
- [x] P0 eight-tool catalog.
- [x] no unrestricted SQL tool.
- [x] WebSearch adapter port.
- [x] SafeWebFetch adapter with SSRF validation.
- [x] all DNS answers validated; any unsafe address fails closed.
- [x] validated IP pin passed to HTTP transport.
- [x] redirect target revalidation on every hop.
- [x] loopback/private/link-local/metadata/Docker host blocking.
- [x] P0 port/content-type/response-size/redirect/time restrictions.
- [x] no ambient Authorization/Cookie injection in fetch adapter.
- [x] SandboxExecute adapter only calls NODE-21 service port with argv.
- [x] Tool Gateway package retains zero third-party runtime dependencies.
- [x] privileged import/secret/socket architecture validator authored.
- [x] global pytest/Pyright discovery includes Tool Gateway.
- [x] deterministic unit/security tests authored.
- [x] deterministic cross-boundary integration smoke authored.
- [x] local `make tool-gateway-contract` entry authored.
- [x] dedicated staged GitHub Actions workflow authored.

## P0 catalog

```text
web.search@1.0.0
web.fetch@1.0.0
asset.read@1.0.0
asset.write-derived@1.0.0
project.query@1.0.0
artifact.query@1.0.0
sandbox.execute@1.0.0
media.inspect@1.0.0
```

## Security evidence authored

The suites explicitly cover:

1. input schema failure before adapter invocation;
2. empty Agent allowlist default deny;
3. wrong Agent tool pattern deny;
4. subagent cannot expand parent tool scope;
5. empty parent scope means a subagent has zero tools;
6. high-risk HITL blocks adapter/SideEffect execution;
7. write definition cannot opt out of idempotency;
8. missing write idempotency key fails closed;
9. missing SideEffectGuard fails closed;
10. duplicate write replays without second adapter call;
11. adapter timeout normalization;
12. arbitrary adapter exception normalization and audit;
13. malformed adapter output rejection;
14. large output offload rather than Agent-context flooding;
15. secret-like argument redaction;
16. loopback/private/link-local/metadata SSRF blocking;
17. mixed public/private DNS result fails closed;
18. validated DNS IP is pinned into transport contract;
19. public -> metadata redirect is rejected before second fetch;
20. unsupported web content types are rejected;
21. web response-size limit is enforced;
22. Search result normalization/cap;
23. Sandbox execute uses isolated service port and argv contract;
24. P0 catalog has exactly eight intended tools and no SQL tool.

## Cross-node boundary

NODE-25 intentionally does not duplicate upstream correctness ownership:

```text
NODE-16 -> authenticated tenant / membership / RBAC
NODE-20 -> durable write idempotency, lease, replay, reconciliation, ambiguity
NODE-21 -> isolated process/filesystem/network execution
NODE-18 -> object storage / Asset validation / Artifact storage
NODE-25 -> tool versioning, permission, risk, HITL, validation, adapter orchestration, audit
```

The Tool Gateway `SideEffectGuard`, `SandboxExecutor`, and `ResultOffloader` ports are the production composition seams for those upstream services.

## Required green evidence before COMPLETE

- [ ] Python compile gate PASS.
- [ ] NODE-25 architecture/security validator PASS.
- [ ] Tool Gateway unit/security tests PASS.
- [ ] deterministic Tool Gateway integration PASS.
- [ ] NODE-20 idempotency static boundary remains consistent.
- [ ] NODE-21 sandbox static boundary remains consistent.
- [ ] frozen `uv sync --all-packages --frozen` PASS.
- [ ] targeted Ruff PASS.
- [ ] targeted Pyright PASS.
- [ ] global repository test discovery includes NODE-25 tests.
- [ ] hosted GitHub Actions jobs actually receive runners and execute.

NODE-25 must remain **not COMPLETE** until required gates execute green. If the repository-level GitHub Actions payment/spending-limit blocker persists, record the exact run/job annotation as external infrastructure evidence rather than describing it as a Tool Gateway test failure.

Next node: **NODE-26 — MCP Integration**.
