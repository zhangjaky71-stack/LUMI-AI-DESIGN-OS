# NODE-26 Acceptance — MCP Integration

Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**

## Delivered

- [x] MCP `2026-07-28` frozen protocol constant and stateless modern request path.
- [x] isolated `2025-11-25` initialize/session compatibility path.
- [x] administrator-controlled MCP Server Registry.
- [x] registered + approved + enabled server requirement.
- [x] global vs organization-scoped server enforcement.
- [x] server remote-tool allow patterns.
- [x] registration-time and request-time SSRF/DNS/IP validation.
- [x] HTTPS-only remote MCP endpoints.
- [x] 2026 protocol restricted to Streamable HTTP.
- [x] trusted `ValidatedTarget` transport contract.
- [x] Agent never supplies MCP base URL.
- [x] credentials bound to both organization and server ID.
- [x] auth cannot override Host/Cookie/MCP routing/session/content headers.
- [x] modern protocol/method/name header contract.
- [x] modern `_meta` protocolVersion/clientCapabilities/clientInfo envelope.
- [x] fresh JSON-RPC request ID per modern request.
- [x] no modern `Mcp-Session-Id` state.
- [x] `server/discover` and bounded `tools/list` discovery.
- [x] strict modern `ttlMs/cacheScope` validation.
- [x] `ttlMs=0` produces no discovery cache entry.
- [x] tenant-keyed discovery cache.
- [x] execution results excluded from discovery cache.
- [x] discovered tool requires exact LUMI `MCPToolPolicy` before publication.
- [x] namespaced `mcp.<server>.<tool>` definitions and collision rejection.
- [x] server annotations cannot choose LUMI risk/idempotency.
- [x] MCP write policies require idempotency.
- [x] safe JSON Schema subset enforcement with byte/depth checks.
- [x] unsupported JSON Schema 2020-12 semantics fail closed rather than being ignored.
- [x] untrusted `x-mcp-header` mapping rejected.
- [x] MCPToolAdapter remains behind NODE-25 Tool Gateway.
- [x] NODE-25 Audit/HITL remains before MCP write side effects.
- [x] NODE-20 SideEffect guard remains around MCP writes.
- [x] MRTR `input_required` fails closed with sanitized correlation metadata.
- [x] malformed `input_required` without inputRequests/requestState rejected.
- [x] raw remote prompts/requestState content are not auto-forwarded.
- [x] raw JSON-RPC errors sanitized.
- [x] modern/legacy deterministic fixtures authored.
- [x] six NODE-26 contract schema exports authored.
- [x] exactly seven explicit NODE-26 gaps recorded.
- [x] one canonical active validator: `tools/node26/validate_mcp.py`.
- [x] one canonical active workflow: `.github/workflows/node-26-mcp-integration.yml`.

## Failure-injection / security evidence authored

The suites and validator explicitly cover:

1. unregistered, unapproved and disabled server denial;
2. cross-tenant server denial;
3. private/internal server destination rejection;
4. cleartext MCP endpoint rejection;
5. 2026 + legacy HTTP/SSE transport rejection;
6. runtime DNS/IP revalidation;
7. transport receives a validated/pinned target;
8. credential organization mismatch rejected before network;
9. credential server mismatch rejected before network;
10. auth cannot overwrite MCP/security headers;
11. modern header/body/_meta consistency;
12. independent modern calls without session state;
13. strict cache hint validation;
14. zero-TTL discovery is not cached;
15. tenant-scoped cache isolation/expiry;
16. tool execution results are never discovery-cached;
17. newly discovered unapproved tool remains unavailable;
18. server `readOnlyHint` cannot downgrade an admin-classified write;
19. write MCP policy cannot opt out of idempotency;
20. NODE-25 HITL prevents network call before approval;
21. approved duplicate write replays rather than performing a second remote write;
22. malicious remote names and normalized namespace collisions are rejected;
23. unsupported schema constraints are rejected;
24. `x-mcp-header` cannot promote Agent input into transport headers;
25. MRTR raw prompt text does not escape through the exception;
26. malformed MRTR result is rejected;
27. HTTP auth failure and JSON-RPC error bodies are sanitized;
28. legacy initialize/session state remains isolated in `legacy.py`;
29. credential value is not copied into Tool Audit.

## Cross-node boundary

```text
NODE-16 -> identity / organization membership / RBAC
NODE-20 -> durable write idempotency / replay / reconciliation
NODE-21 -> isolated code execution
NODE-25 -> tool permission / risk / HITL / schema / offload / audit
NODE-26 -> approved MCP registry, protocol compatibility and MCP adapter mapping
```

MCP never replaces these upstream boundaries.

## Contract artifacts

`tools/node26/export_mcp_schemas.py` emits exactly six schemas:

```text
mcp-server-definition.schema.json
mcp-tool-policy.schema.json
mcp-discovered-tool.schema.json
mcp-discovery-result.schema.json
mcp-request-auth.schema.json
mcp-call-result.schema.json
```

## Explicit limitations / gaps

The canonical `gap-ledger.json` contains exactly seven items:

1. `MCP-COMPOSITION-001` — durable Registry/Policy/admin persistence and DI not composed.
2. `MCP-TRANSPORT-002` — production TLS/SNI-aware pinned-IP HTTP/SSE transport and byte-budget hardening not bound.
3. `MCP-SCHEMA-003` — full JSON Schema 2020-12 execution is not implemented; unsupported semantics fail closed.
4. `MCP-MRTR-004` — durable LUMI-owned input/HITL resume is not implemented.
5. `MCP-AUTH-005` — real Secret Manager/OAuth refresh/revocation/principal mapping not composed.
6. `MCP-COMPAT-006` — broader real MCP server/SDK compatibility matrix remains future validation.
7. `MCP-CI-007` — Hosted Actions remain blocked by account billing/spending-limit state.

## Required green evidence before COMPLETE

- [ ] frozen `uv sync --all-packages --frozen` actually executes and passes;
- [ ] NODE-25 active validator actually executes and passes;
- [ ] NODE-26 active architecture/security validator actually executes and passes;
- [ ] Tool Gateway + MCP pytest suite actually executes and passes;
- [ ] deterministic MCP → Tool Gateway integration actually executes and passes;
- [ ] six schemas + seven gaps validation actually executes and passes;
- [ ] targeted Ruff actually executes and passes;
- [ ] targeted Pyright actually executes and passes;
- [ ] hosted job receives a runner (`runner_id != 0`) and contains executed steps.

No hosted PASS may be inferred from workflow configuration alone. If GitHub reports `runner_id=0` and `steps=[]`, the node remains `BLOCKED_EXTERNAL` rather than being classified as source failure or PASS.

## Next

**NODE-27 — Cost Ledger**.
