# NODE-26 Acceptance — MCP Integration

Status: **IMPLEMENTED / VALIDATING**

## Delivered

- [x] MCP 2026-07-28 protocol constant and stateless request path.
- [x] isolated 2025-11-25 legacy initialize/session compatibility path.
- [x] administrator-approved MCP Server Registry.
- [x] enabled/approved server enforcement.
- [x] global vs organization-scoped server enforcement.
- [x] server tool-pattern allowlist.
- [x] registration-time SSRF validation.
- [x] request-time DNS/IP revalidation.
- [x] pinned `ValidatedTarget` HTTP transport port.
- [x] Agent never supplies MCP base URL.
- [x] tenant-bound credential provider contract.
- [x] auth headers cannot override MCP routing/security headers or Cookie/Host.
- [x] modern `MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name` header contract.
- [x] modern `_meta` protocolVersion/clientCapabilities/clientInfo envelope.
- [x] fresh JSON-RPC request ID for each modern request.
- [x] `server/discover` protocol/capability path.
- [x] bounded/paginated `tools/list` discovery.
- [x] tenant-scoped discovery cache with TTL.
- [x] execution results excluded from discovery cache.
- [x] MCP tool descriptors treated as untrusted metadata.
- [x] exact admin `MCPToolPolicy` required before ToolDefinition publication.
- [x] namespaced `mcp.<server>.<tool>` LUMI definitions.
- [x] normalized-name collision rejection.
- [x] server annotations cannot determine LUMI risk/idempotency.
- [x] write-class MCP policies require idempotency.
- [x] schema byte/depth limits.
- [x] unsupported JSON Schema semantics fail closed.
- [x] P0 `x-mcp-header` mapping rejected.
- [x] MCPToolAdapter implements NODE-25 ToolAdapter boundary.
- [x] Tool Gateway HITL remains before MCP external writes.
- [x] Tool Gateway SideEffect guard remains around MCP writes.
- [x] MRTR `input_required` fails closed through sanitized `MCP_INPUT_REQUIRED`.
- [x] raw elicitation/sampling prompt bodies are not auto-forwarded to Agent/user.
- [x] complete structured MCP output passes back through NODE-25 output schema/offload.
- [x] raw JSON-RPC errors sanitized.
- [x] deterministic modern mock transport tests.
- [x] different modern fake instances can serve consecutive calls with no session.
- [x] deterministic legacy session fixture.
- [x] MCP -> Tool Gateway integration smoke authored.
- [x] architecture/security validator authored.
- [x] detailed runtime specification authored.
- [x] dedicated CI workflow authored.

## Current protocol evidence

NODE-26 is implemented against the MCP **2026-07-28** wire model verified against the current official specification/schema during implementation. The code freezes the protocol string so future spec revisions do not silently change runtime semantics.

Modern requests prove:

```text
MCP-Protocol-Version == params._meta protocolVersion
Mcp-Method == JSON-RPC method
Mcp-Name == remote tool name for tools/call
fresh JSON-RPC id per request
no Mcp-Session-Id
```

## Security evidence authored

The deterministic suites verify:

1. unregistered MCP server is unusable;
2. unapproved MCP server is unusable;
3. disabled MCP server is unusable;
4. organization-scoped MCP server cannot cross tenants;
5. private/internal server target is rejected by SSRF policy;
6. server DNS/IP is revalidated at runtime rather than permanently cached;
7. transport receives a validated/pinned target;
8. credential object is organization-bound;
9. credential tenant mismatch fails closed;
10. auth cannot override Host/Cookie/MCP routing headers;
11. current MCP headers and `_meta` are consistent;
12. current calls have no session header;
13. consecutive modern calls may hit different server instances;
14. discovery cache avoids repeated list/discover calls;
15. discovery cache remains organization scoped;
16. cache expires deterministically;
17. `tools/call` does not use discovery result cache;
18. newly discovered tool without admin policy is not registered;
19. MCP read-only/destructive annotations do not override LUMI admin risk;
20. MCP write policy cannot set idempotency NOT_REQUIRED;
21. MCP write still returns Tool Gateway APPROVAL_REQUIRED before network call;
22. approved duplicate MCP write replays with one remote invocation;
23. malicious remote tool name is rejected;
24. namespacing collision is rejected;
25. unsupported schema semantics are rejected;
26. untrusted `x-mcp-header` is rejected;
27. input/output schema still pass through NODE-25 validation;
28. `input_required` exposes only correlation keys / state presence to LUMI policy;
29. raw MRTR prompt content is not surfaced by the exception;
30. HTTP auth failure is normalized;
31. raw JSON-RPC error message/data do not escape;
32. legacy initialize occurs once per legacy server/organization session;
33. legacy session headers stay in `legacy.py`, not modern client;
34. MCP credential value is absent from Tool Audit.

## Cross-node correctness boundary

```text
NODE-16 -> identity / organization membership / RBAC
NODE-20 -> durable side-effect idempotency / replay / reconciliation
NODE-21 -> isolated code execution
NODE-25 -> tool permission / risk / HITL / validation / audit
NODE-26 -> approved MCP server discovery, wire compatibility and adapter mapping
```

MCP is not permitted to bypass any prior boundary.

## P0 limitations / deliberate follow-ups

- MCP Server Registry and MCPToolPolicy are runtime/in-memory contracts; durable admin persistence comes later.
- No Agent-controlled MCP server URL.
- No stdio MCP transport in P0 Tool Gateway.
- No public LUMI MCP server.
- No automatic MRTR elicitation/sampling fulfillment; `input_required` is fail-closed until a LUMI-owned HITL/input resume flow is implemented.
- No live MCP credential/server is needed for deterministic acceptance.
- HTTP/SSE parsing and TLS/pinned-IP connection implementation live behind `MCPHTTPTransport`.

## Required green evidence before COMPLETE

- [ ] Python compile gate PASS.
- [ ] NODE-26 MCP architecture/security validator PASS.
- [ ] NODE-25 Tool Gateway architecture/security validator remains PASS.
- [ ] all Tool Gateway/MCP unit/security tests PASS.
- [ ] MCP -> Tool Gateway deterministic integration PASS.
- [ ] frozen `uv sync --all-packages --frozen` PASS.
- [ ] targeted Ruff PASS.
- [ ] targeted Pyright PASS.
- [ ] hosted GitHub Actions jobs actually receive runners and execute.

NODE-26 is not COMPLETE until required hosted gates execute green. If the repository-level GitHub Actions payment/spending-limit blocker persists, record exact run/job evidence and keep status **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL / not COMPLETE**.

Next node: **NODE-27 — Cost Ledger**.
