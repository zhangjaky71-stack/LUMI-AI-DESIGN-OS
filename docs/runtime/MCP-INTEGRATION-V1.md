# MCP Integration V1

> NODE-26 runtime/security contract.  
> Depends on NODE-25 Tool Gateway.  
> Preferred protocol baseline: **MCP 2026-07-28**.  
> Legacy `2025-11-25` support is compatibility-only and isolated behind the legacy adapter.

## 1. Responsibility

MCP is an integration protocol, not a second authorization or execution authority.

The only Agent-facing flow is:

```text
Agent
→ ToolGatewayClient
→ NODE-25 Tool Gateway
   → Registry/version resolution
   → tenant/tool permissions
   → risk + HITL
   → input validation
   → NODE-20 SideEffect guard for writes
   → MCPToolAdapter
      → approved MCP Server Registry
      → tenant/server-bound credential provider
      → SSRF validated runtime target
      → trusted pinned transport
      → MCP wire protocol
   → output validation/offload
   → Audit
→ Agent
```

Forbidden paths include:

```text
Agent → arbitrary MCP URL
Agent → MCP SDK directly
Agent → MCP server credential
Agent → discovered-but-unapproved MCP tool
Agent → production DB/storage/network authority through MCP
```

NODE-26 does not weaken any NODE-25 permission, HITL, timeout, audit or idempotency invariant.

## 2. Protocol baseline

### 2.1 Modern path — 2026-07-28

The preferred path is stateless per request. Each request uses:

- a fresh JSON-RPC request ID;
- `MCP-Protocol-Version: 2026-07-28`;
- `Mcp-Method` matching the JSON-RPC method;
- `Mcp-Name` for named calls such as `tools/call`;
- `params._meta` containing protocol version, client capabilities and client info;
- no modern `Mcp-Session-Id` state.

The modern client supports:

```text
server/discover
tools/list
tools/call
```

`resultType` is mandatory on 2026-era results. Header routing is treated only as a routing aid; response/body structure is still validated.

### 2.2 Modern transport

A server advertising `2026-07-28` must be configured with:

```text
transport = streamable_http
```

`legacy_http_sse` + `2026-07-28` fails construction with:

```text
MCP_2026_TRANSPORT_INVALID
```

P0 remote MCP endpoints must use HTTPS. Cleartext HTTP fails construction with:

```text
MCP_SERVER_TLS_REQUIRED
```

The trusted `MCPHTTPTransport` port receives a `ValidatedTarget` containing the approved host and pinned public IP. A production implementation must preserve TLS certificate validation/SNI for the approved hostname while connecting to the validated IP and must not silently re-resolve the host.

### 2.3 Legacy compatibility

`2025-11-25` compatibility lives only in `mcp/legacy.py` and owns:

```text
initialize
notifications/initialized
Mcp-Session-Id when provided
tools/list
tools/call
```

Legacy session state is keyed by MCP server and organization. Modern `mcp/client.py` contains no session ID state.

A server can use the legacy path only when the administrator explicitly configured the legacy protocol version. Compatibility never changes LUMI permissions or risk classification.

## 3. MCP Server Registry

Agents do not provide base URLs. `MCPServerRegistry` contains administrator-controlled definitions:

```text
server_id
name
base_url
transport
enabled
approved
trust_level
organization_id | global
allowed_tool_patterns
protocol_versions
auth_profile
auth_header_names
network_policy
discovery_ttl_seconds
```

A server must be both approved and enabled. Organization-scoped servers reject other tenants.

### 3.1 Network validation

Server registration immediately validates the URL through NODE-25 `SSRFPolicy`.

Every runtime request validates the same URL again:

```text
runtime_target()
→ SSRFPolicy.validate()
→ ValidatedTarget
```

This prevents registration-time DNS results from becoming permanent trust. Loopback, private, link-local, metadata, Docker-host aliases and non-global IPs remain blocked by NODE-25.

## 4. Credentials

Credentials are injected server-side through:

```text
MCPCredentialProvider.credentials_for(server, organization_id)
```

`MCPRequestAuth` is bound to both:

```text
organization_id
server_id
```

A tenant mismatch or server mismatch fails before transport execution.

Credential material is not present in `ToolRequest`, Agent context or Tool Audit. Credential providers cannot override reserved routing/security headers such as Host, Cookie, MCP protocol/method/name/session headers, Content-Type or Accept.

Production Secret Manager/OAuth refresh/revocation is outside this node and remains explicit in the gap ledger.

## 5. Discovery and cache

Discovery is metadata, never authorization.

```text
server/discover
→ tools/list
→ MCPDiscoveredTool[]
→ exact MCPToolPolicy lookup
→ approved ToolDefinition[]
```

A newly discovered tool without an administrator policy receives no Tool Gateway registration.

### 5.1 2026 cacheable-result rules

For the modern path, `server/discover` and each `tools/list` page require valid:

```text
ttlMs >= 0
cacheScope = private | public
```

Malformed/missing cache hints fail closed with `MCP_PROTOCOL_MISMATCH` rather than silently inventing cache semantics.

`ttlMs = 0` means immediately stale and therefore is not inserted into the discovery cache.

Cache keys always include:

```text
server_id + organization_id
```

Even when remote metadata says `public`, P0 remains tenant-keyed. Tool execution results are never stored in `MCPDiscoveryCache`; write replay belongs only to NODE-20.

## 6. Tool mapping

Discovered remote tools are mapped to namespaced LUMI tools:

```text
mcp.<server_id>.<normalized-remote-name>
```

The mapper rejects namespace collisions.

The server's description and annotations do not control security. `MCPToolPolicy` is the authority for:

```text
risk
permissions
idempotency
timeout
max inline output
sensitive fields
```

Write/destructive/financial/privileged tools must declare `idempotency=REQUIRED`. NODE-25 still applies approval and NODE-20 still owns durable replay/reconciliation.

## 7. JSON Schema trust boundary

MCP 2026 tool schemas are JSON Schema 2020-12 data, but the current NODE-25 validator intentionally implements a deterministic safe subset.

NODE-26 therefore does **not** claim full JSON Schema 2020-12 execution support.

The mapper checks schema JSON serializability, byte limits, recursion depth and supported keywords. Unsupported semantics such as `$ref`, combinators, `pattern`, `format` or untrusted `x-mcp-header` mappings fail closed instead of being silently ignored.

This prevents a remote server from advertising a stricter schema than LUMI can actually enforce.

Full JSON Schema 2020-12 compatibility remains `MCP-SCHEMA-003`.

## 8. MRTR / input_required

A modern tool may return:

```text
resultType = input_required
inputRequests = {...}?
requestState = opaque string?
```

An `input_required` response with neither `inputRequests` nor `requestState` is rejected as malformed.

P0 does not automatically fulfill remote elicitation/sampling requests. `MCPToolAdapter` raises sanitized:

```text
MCP_INPUT_REQUIRED
```

Only safe correlation metadata is surfaced:

- server ID;
- remote tool name;
- input request keys;
- whether opaque requestState exists.

Raw prompt bodies and requestState contents are not forwarded directly to the Agent/user. Durable LUMI-owned HITL/input collection and bounded resume belongs to later orchestration work.

## 9. Output and error normalization

Complete MCP results are normalized into `ToolAdapterOutput` and then pass through NODE-25 output validation and large-result offload.

Raw JSON-RPC `message`/`data`, credentials and protocol internals are not returned to Agent context.

Stable MCP errors include:

```text
MCP_SERVER_UNAVAILABLE
MCP_PROTOCOL_MISMATCH
MCP_TOOL_NOT_FOUND
MCP_SCHEMA_INVALID
MCP_AUTH_FAILED
MCP_POLICY_DENIED
MCP_INPUT_REQUIRED
```

## 10. Integration plan

`MCPIntegrationBuilder.prepare()` returns:

```text
MCPIntegrationPlan {
  server_id
  protocol_version
  approved ToolDefinition[]
  exact ToolAdapter map
}
```

Only explicitly approved remote tools can appear in the plan. The application composition root can merge the plan with native NODE-25 definitions/adapters before constructing Tool Gateway.

## 11. P0 security invariants

1. Agent never supplies an MCP server URL.
2. MCP server must be registered, approved and enabled.
3. Organization scope must match.
4. Remote endpoint must be HTTPS and SSRF-safe.
5. 2026 protocol uses Streamable HTTP only.
6. DNS/IP policy is rechecked on every request.
7. Credential is bound to both organization and server.
8. Discovered tool is not authorization.
9. Risk/idempotency come from LUMI policy, not MCP annotations.
10. Write MCP tools still require NODE-25 Audit/HITL and NODE-20 SideEffect semantics.
11. Modern tool execution results are not cached by MCP integration.
12. MRTR does not bypass LUMI-owned user-input policy.
13. Unsupported schema semantics fail closed.
14. Modern path contains no legacy session state.
15. MCP core does not import HTTP clients, DB drivers, Docker, subprocess or an MCP SDK directly.

## 12. Acceptance assets

Canonical active assets:

```text
services/tool-gateway/src/lumi_tool_gateway/mcp/**
services/tool-gateway/tests/test_mcp_*.py
scripts/integration_mcp_tool_gateway.py
tools/node26/validate_mcp.py
tools/node26/export_mcp_schemas.py
reports/nodes/NODE-26/acceptance.md
reports/nodes/NODE-26/gap-ledger.json
.github/workflows/node-26-mcp-integration.yml
```

The schema exporter emits six contract schemas. The gap ledger contains exactly seven explicit gaps.

The dedicated hosted workflow is intended to run:

```text
frozen uv sync
compile
NODE-25 validator recheck
NODE-26 architecture/security validator
Tool Gateway + MCP tests
deterministic MCP→Tool Gateway integration
6 schema + 7 gap validation
Ruff
Pyright
```

No live MCP server or production credential is required for deterministic acceptance.

## 13. Explicit gaps

The canonical gap ledger owns:

```text
MCP-COMPOSITION-001
MCP-TRANSPORT-002
MCP-SCHEMA-003
MCP-MRTR-004
MCP-AUTH-005
MCP-COMPAT-006
MCP-CI-007
```

NODE-26 remains **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL** until hosted gates actually receive a runner and execute.

## 14. Scope boundary

NODE-26 implements LUMI as an MCP client/integration consumer only. A public LUMI MCP server is a separate P2 surface and is not activated here.

## 15. Next node

**NODE-27 — Cost Ledger**.
