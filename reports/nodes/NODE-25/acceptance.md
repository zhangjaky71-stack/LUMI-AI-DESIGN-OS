# NODE-25 Acceptance — Tool Gateway

Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**

## Delivered

- [x] provider-neutral `ToolDefinition` / `ToolRequest` / `ToolResult` contracts.
- [x] exact-semver and `major.x` Tool Registry resolution.
- [x] frozen risk tiers: READ_INTERNAL / READ_EXTERNAL / WRITE_INTERNAL / WRITE_EXTERNAL / DESTRUCTIVE / FINANCIAL / PRIVILEGED.
- [x] runtime types: native / mcp / sandbox; MCP activation explicitly deferred to NODE-26.
- [x] default-deny Agent tool allowlist.
- [x] Organization allow/deny narrowing.
- [x] root-vs-subagent parent scope semantics; child scope cannot widen parent scope.
- [x] required permission-scope intersection.
- [x] input schema validation before approval/effect execution.
- [x] output schema validation before Agent return/offload.
- [x] HITL contract before WRITE_EXTERNAL / DESTRUCTIVE / FINANCIAL / PRIVILEGED execution.
- [x] approval token presence alone never counts as approval.
- [x] every write-class definition must declare idempotency REQUIRED.
- [x] Tool idempotency key maximum aligned to NODE-20 at 255 characters.
- [x] Tool operation identity aligned to NODE-20 maximum 100 characters.
- [x] write call requires SideEffectGuard.
- [x] write call fails closed without AuditSink before approval/effect execution.
- [x] deterministic reference guard uses semantic request hash and concurrency lock.
- [x] duplicate same-semantic write replay invokes adapter once.
- [x] same key + different semantic request raises stable Tool idempotency conflict.
- [x] active NODE-20 bridge composes current `SideEffectGateway` + `MemoryIdempotencyStore` and proves replay/conflict semantics.
- [x] bounded tool timeout and normalized adapter/internal errors.
- [x] large structured output offload with bounded inline preview and `full_result_ref`.
- [x] structured Audit with recursive secret-field redaction.
- [x] adapter output bodies/raw exception messages are not copied into Audit.
- [x] exact P0 eight-tool catalog.
- [x] no unrestricted SQL tool.
- [x] WebSearch adapter port.
- [x] SafeWebFetch adapter with HTTP/HTTPS, port, DNS/IP, metadata/private/loopback protections.
- [x] every DNS answer must be public; mixed public/private answers fail closed.
- [x] validated IP is pinned into transport contract.
- [x] every redirect target is revalidated before the next fetch.
- [x] response byte/content-type/redirect/timeout limits.
- [x] no ambient Authorization/Cookie injection.
- [x] Sandbox adapter only calls a narrow NODE-21 executor port with argv; no host shell/Docker socket path.
- [x] Tool Gateway reusable core retains `dependencies = []`.
- [x] architecture validator rejects direct asyncpg/SQLAlchemy/psycopg/boto3/Docker/subprocess authority in Tool Gateway core.
- [x] workspace pytest discovery includes Tool Gateway tests without restoring deprecated old-chain packages.
- [x] deterministic unit/security/integration suites authored.
- [x] six JSON Schema exports authored.
- [x] active-chain cross-node integration mapping documented.
- [x] exact seven-gap ledger authored.
- [x] dedicated NODE-25 Hosted workflow authored.

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

## Security / correctness evidence authored

The suites cover at least:

1. exact and major-range version resolution;
2. input schema failure before adapter;
3. empty Agent allowlist default deny;
4. forbidden tool pattern;
5. subagent cannot expand parent scope;
6. empty parent scope means zero child tools;
7. high-risk HITL blocks side effect before approval;
8. write definition cannot disable idempotency;
9. write without AuditSink fails before approval/effect;
10. missing idempotency key fails closed;
11. missing SideEffectGuard fails closed;
12. NODE-20-compatible 255-character idempotency maximum;
13. NODE-20-compatible operation type maximum;
14. duplicate write replay invokes adapter once;
15. concurrent duplicate write invokes adapter once;
16. same key / different semantic request conflict;
17. real active NODE-20 SideEffectGateway bridge replay/conflict;
18. adapter timeout normalization;
19. arbitrary adapter exception normalization and safe Audit;
20. invalid adapter output rejection;
21. large output offload rather than Agent-context flooding;
22. recursive secret-like argument redaction;
23. loopback/private/link-local/metadata/Docker-host SSRF rejection;
24. mixed DNS fail closed;
25. validated IP pinned into transport contract;
26. redirect-to-metadata rejected before second fetch;
27. unsupported content type rejected;
28. response size limit enforced;
29. P0 catalog/no-SQL invariant;
30. WebSearch normalization/cap;
31. Sandbox argv/service-port boundary;
32. Agent client exposes `invoke()` rather than server registry/adapters.

## Cross-node boundary

```text
NODE-16 -> authenticated tenant / membership / RBAC source
NODE-18 -> trusted Asset/Object storage and production large-result offload
NODE-20 -> durable side-effect identity/replay/conflict/recovery
NODE-21 -> isolated execution and resource/network/filesystem enforcement
NODE-25 -> tool version/permission/risk/HITL/schema/adapter/orchestration/audit boundary
NODE-26 -> MCP adapter and connection policy
NODE-28/62 -> durable approval interrupt/resume and governance
NODE-65 -> durable append-only audit retention/governance
```

The active implementation deliberately does not grant Tool Gateway core database, object-store, provider, Docker or shell credentials.

## Explicit unresolved gaps

The source of truth is `reports/nodes/NODE-25/gap-ledger.json` and contains exactly:

1. `TOOL-COMPOSITION-001`
2. `TOOL-WEB-002`
3. `TOOL-APPROVAL-003`
4. `TOOL-MCP-004`
5. `TOOL-AUDIT-005`
6. `TOOL-NATIVE-006`
7. `TOOL-CI-007`

These gaps do not authorize bypassing the Gateway. Missing bindings remain unavailable/fail-closed.

## Required green evidence before COMPLETE

- [ ] active NODE-25 static architecture/security validator PASS on Hosted runner.
- [ ] Tool Gateway unit/security tests PASS on Hosted runner.
- [ ] deterministic Tool Gateway integration PASS on Hosted runner.
- [ ] active NODE-20 bridge PASS on Hosted runner.
- [ ] active NODE-20 validator remains consistent.
- [ ] active NODE-21 sandbox validators remain consistent.
- [ ] six schema exports validate.
- [ ] frozen `uv sync --all-packages --frozen` PASS.
- [ ] targeted Ruff PASS.
- [ ] targeted Pyright PASS.
- [ ] Hosted GitHub Actions actually receives a runner and executes steps.

No canonical pytest/Ruff/Pyright/security/integration PASS is claimed from source inspection alone. If GitHub reports the known payment/spending-limit condition with `runner_id=0` and `steps=[]`, classify it as **BLOCKED_EXTERNAL**, not a Tool Gateway source failure.

Canonical runtime contract: `docs/runtime/TOOL-GATEWAY-V1.md`  
Active integration mapping: `docs/runtime/TOOL-GATEWAY-INTEGRATION-V1.md`

Next node: **NODE-26 — MCP Integration**.
