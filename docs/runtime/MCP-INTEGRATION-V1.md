# MCP Integration V1

> NODE-26 runtime/security contract.  
> Depends on NODE-25 Tool Gateway.  
> Protocol baseline verified against the MCP **2026-07-28** specification and official schema; `2025-11-25` is retained only behind a compatibility adapter.

## 1. Architectural rule

MCP is an integration transport, **not** a second authorization plane.

The only allowed Agent flow is:

```text
Agent
  -> ToolGatewayClient
  -> NODE-25 Tool Gateway
       Registry/version resolution
       tenant/tool permission
       risk/HITL
       input schema
       NODE-20 SideEffect guard for writes
       MCPToolAdapter
          approved MCP Server Registry
          trusted credential provider
          SSRF-validated/pinned transport
          MCP protocol
       output schema
       offload
       Audit
  -> Agent
```

The following is forbidden:

```text
Agent -> arbitrary MCP URL
Agent -> MCP SDK directly
Agent -> MCP credential
Agent -> MCP-discovered tool without Tool Gateway policy
```

NODE-26 therefore extends the NODE-25 adapter surface without changing NODE-25 permission, HITL, idempotency, timeout, output or audit semantics.

## 2. Protocol strategy

### 2.1 Preferred protocol

The preferred wire revision is:

```text
2026-07-28
```

The NODE-26 modern path follows the current protocol model:

- each client request is independent;
- JSON-RPC requests use fresh request IDs;
- HTTP carries `MCP-Protocol-Version`;
- `Mcp-Method` mirrors the JSON-RPC method;
- `Mcp-Name` is supplied for named operations such as `tools/call`;
- request `params._meta` carries the protocol version and client capability envelope;
- `resultType` is required on 2026-era results;
- `server/discover` is used for protocol/capability discovery;
- tool metadata is obtained through `tools/list`;
- `input_required` is the multi-round-trip result form;
- modern execution does not rely on `Mcp-Session-Id`.

`MCPHTTPTransport` normalizes either JSON or request-scoped SSE into an `MCPHTTPResponse`; JSON/SSE parsing is a transport concern and does not leak into Tool Gateway domain models.

### 2.2 Legacy compatibility

`2025-11-25` support is isolated in `mcp/legacy.py`.

The legacy compatibility client owns:

```text
initialize
notifications/initialized
optional Mcp-Session-Id
legacy tools/list
tools/call
```

Modern `mcp/client.py` contains no `Mcp-Session-Id` state.

A server configured for both eras is attempted through the current discovery path first. If the current discovery method is unavailable/protocol-incompatible and the administrator explicitly allowed the legacy revision, the client may fall back to the legacy adapter.

Legacy compatibility is not permission compatibility: every resulting remote tool is still mapped through the same NODE-25 policy pipeline.

## 3. MCP Server Registry

Agents never provide an MCP base URL.

`MCPServerRegistry` stores administrator-controlled definitions:

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
network_policy
discovery_ttl_seconds
```

A server must be both:

```text
approved == true
enabled == true
```

If `organization_id` is set, any other tenant is rejected.

The server allowlist controls which remote tool names are even eligible for mapping.

## 4. Network / SSRF boundary

NODE-26 reuses NODE-25 `SSRFPolicy`.

### 4.1 Admin registration

When a server definition is registered, its base URL is validated immediately.

### 4.2 Runtime revalidation

Registration-time validation is not trusted forever.

Every MCP request calls:

```text
MCPServerRegistry.runtime_target(...)
-> SSRFPolicy.validate(base_url)
-> ValidatedTarget(pinned_ip, hostname, port, ...)
```

Thus DNS/IP policy is re-evaluated at request time.

### 4.3 Transport rule

`MCPHTTPTransport.post()` receives a `ValidatedTarget` instead of an arbitrary URL string.

A production transport MUST:

- connect to the validated/pinned IP;
- preserve TLS certificate validation/SNI for the approved hostname;
- disable automatic redirect following, or return the redirect to a trusted layer that performs the same SSRF validation before a new request;
- not re-resolve the hostname behind the security layer;
- not use ambient browser cookies or application credentials.

NODE-26 treats unexpected 3xx responses as protocol failures; it does not provide an Agent-controlled redirect path.

## 5. Authentication boundary

MCP credentials are injected through:

```text
MCPCredentialProvider.credentials_for(server, organization_id)
```

The provider returns `MCPRequestAuth` bound to the same `organization_id`.

A credential with a mismatched organization is rejected before transport execution.

`MCPRequestAuth` cannot override routing/security headers including:

```text
Host
Cookie
MCP-Protocol-Version
Mcp-Method
Mcp-Name
Mcp-Session-Id
Content-Type
Accept
```

Authorization or other explicitly trusted auth headers may be returned by the credential provider, but credentials are never fields in `ToolRequest`, `ToolDefinition`, Tool Audit, or MCP-discovered metadata.

A production credential provider should return short-lived delegated/scoped credentials rather than exposing long-lived server secrets to Agents.

## 6. Modern request envelope

Every 2026-era request creates a fresh JSON-RPC ID and contains:

```text
params._meta[io.modelcontextprotocol/protocolVersion]
params._meta[io.modelcontextprotocol/clientCapabilities]
params._meta[io.modelcontextprotocol/clientInfo]
```

The HTTP headers contain matching protocol/method/name bookkeeping.

The test suite verifies header/body consistency and proves two consecutive `tools/call` requests can be served by different fake MCP server instances without a session identifier.

## 7. Discovery does not authorize tools

MCP discovery is evidence about what a server claims to expose. It is **not** an allowlist.

The flow is:

```text
server/discover
-> tools/list
-> MCPDiscoveredTool[]
-> exact administrator MCPToolPolicy lookup
-> ToolDefinition[]
```

If a discovered tool has no administrator `MCPToolPolicy`, it is not published into the LUMI Tool Registry.

A newly appearing remote tool therefore has zero Agent permissions by default.

## 8. Tool mapping and namespacing

Approved remote tools are namespaced as:

```text
mcp.<server_id>.<normalized-remote-name>
```

Example:

```text
server_id = design
remote name = assets.search
-> mcp.design.assets.search
```

Remote names are normalized into NODE-25-compatible lowercase segments. If two remote names normalize to the same LUMI name, discovery fails with a namespace-collision policy error rather than silently choosing one.

Malicious/invalid remote names are rejected before registration.

## 9. Risk is LUMI policy, not MCP metadata

`MCPToolPolicy` is the only authority for:

```text
risk
permissions
idempotency
timeout
inline output limit
sensitive fields
```

NODE-26 deliberately does **not** infer risk from:

```text
description
annotations
readOnlyHint
destructiveHint
server self-description
```

For example, a server may label a tool `readOnlyHint=true`, while LUMI administrators classify it `WRITE_EXTERNAL`; the resulting ToolDefinition remains a write and still requires NODE-25 HITL/idempotency.

Every write-class MCP policy must set `idempotency=REQUIRED`, or construction fails.

## 10. MCP schema trust boundary

MCP input/output schemas are untrusted server input.

Before a remote tool is mapped, NODE-26 checks:

- JSON serializability with non-finite values rejected;
- total schema byte limit;
- recursion depth limit;
- schema key/value structure;
- compatibility with the JSON Schema subset NODE-25 can actually enforce.

Unsupported semantic constraints such as `$ref`, `oneOf`, `pattern`, `format`, and similar keywords fail closed rather than being silently ignored.

This prevents the system from showing a restrictive remote schema while locally validating only a weaker subset.

### 10.1 `x-mcp-header`

NODE-26 P0 rejects `x-mcp-header` mappings.

This is intentional: an untrusted MCP server must not cause arbitrary Agent arguments to be promoted into transport headers. A future trusted implementation may add a separately reviewed header-mapping policy behind the same Tool Gateway boundary.

## 11. Discovery cache

`MCPDiscoveryCache` stores only server/tool metadata.

Cache keys include:

```text
server_id
organization_id
```

TTL is bounded by the LUMI server definition and remote cache hints.

Even if a server marks metadata cacheable as `public`, the P0 in-memory implementation remains tenant-keyed to avoid accidental cross-tenant metadata coupling.

`tools/call` never reads or writes the discovery cache.

Tool execution results—especially writes—are never cached by the MCP integration layer. Write replay remains NODE-20 SideEffect Gateway territory.

## 12. `server/discover` and `tools/list`

The modern client:

1. checks the tenant-approved server definition;
2. uses `server/discover` with the current protocol envelope;
3. negotiates the highest mutually configured supported version;
4. retrieves `tools/list` metadata;
5. follows bounded list pagination;
6. caps discovered tool count;
7. caches only normalized discovery metadata;
8. maps only explicitly approved tools.

A server discovery cache hit never means a tool is authorized—the mapping policy is applied when building the integration plan.

## 13. Multi-round-trip / `input_required`

The current protocol can return:

```text
resultType = input_required
inputRequests = { ... }
requestState = opaque string?
```

NODE-26 P0 intentionally disables automatic fulfillment.

When `MCPToolAdapter` receives `input_required`, it raises a sanitized:

```text
MCP_INPUT_REQUIRED
```

The exception contains only:

```text
server_id
remote tool name
input request correlation keys
whether requestState exists
```

It does **not** forward raw elicitation/sampling prompts, schemas, or requestState content directly to the Agent/user.

This creates a safe bridge point for LUMI's own HITL/input policy. A future resume flow may:

1. inspect the input request under trusted policy;
2. obtain user/admin approval or controlled input;
3. build `inputResponses`;
4. echo the opaque `requestState` byte-for-byte;
5. retry the original MCP request with a **new** JSON-RPC ID;
6. cap the number of rounds.

Until that bridge is implemented and reviewed, `input_required` is fail-closed rather than auto-fulfilled by an untrusted server.

## 14. Tool execution adapter

`MCPToolAdapter` implements the existing NODE-25 `ToolAdapter` protocol.

Before calling the MCP client it verifies:

```text
ToolDefinition.runtime == MCP
resolved LUMI tool name matches adapter mapping
server/tool mapping is exact
```

The client again verifies:

```text
server approved/enabled
tenant scope
remote tool allowed by server policy
protocol version
credential tenant binding
runtime SSRF target
```

Defense-in-depth checks do not replace NODE-25 permission/HITL; they protect the integration boundary itself.

## 15. Output normalization

Complete MCP results are normalized as:

- `structuredContent` when present;
- otherwise a bounded JSON object containing normalized MCP content blocks;
- text content contributes to a bounded Tool summary;
- resource URIs may become `resource_refs`;
- raw protocol headers, credentials, server errors and session metadata are not included.

The resulting value still passes NODE-25 output schema validation and large-result offload policy before it can return to an Agent.

## 16. Error normalization

NODE-26 defines stable error codes including:

```text
MCP_SERVER_UNAVAILABLE
MCP_PROTOCOL_MISMATCH
MCP_TOOL_NOT_FOUND
MCP_SCHEMA_INVALID
MCP_AUTH_FAILED
MCP_POLICY_DENIED
MCP_INPUT_REQUIRED
```

Raw JSON-RPC error `message` and `data` are not propagated.

The test suite injects a remote error containing a fake secret and verifies the secret does not appear in the raised error.

## 17. Legacy security boundary

Legacy compatibility does not relax any LUMI policy.

The only session state lives inside `LegacyMCPClient`, keyed by:

```text
server_id + organization_id
```

The outer ToolDefinition, permission context, HITL, idempotency and audit contracts remain exactly the same as modern MCP.

The legacy fixture verifies `initialize` happens once and subsequent legacy calls use only the isolated session adapter.

## 18. Integration planning

`MCPIntegrationBuilder.prepare()` produces:

```text
MCPIntegrationPlan {
  server_id
  protocol_version
  approved ToolDefinition[]
  exact ToolAdapter map
}
```

The application composition root can merge these definitions/adapters with native NODE-25 tools before constructing Tool Gateway.

`MCPIntegrationBuilder` cannot publish an unapproved discovered tool because the mapper only returns definitions with exact administrator policies.

## 19. Control-plane persistence boundary

NODE-26 P0 implements an immutable/in-memory MCP Server Registry contract and integration planner.

Production persistence for:

```text
approved servers
organization scopes
auth profile references
allowed remote-tool patterns
MCPToolPolicy versions
admin change audit
```

belongs in a later control-plane/admin persistence layer. It must preserve the same runtime interfaces.

P0 intentionally avoids introducing a second ad-hoc database schema merely to make the MCP client functional.

## 20. Public MCP server is not NODE-26

NODE-26 implements LUMI as an MCP **client/integration consumer** only.

Exposing LUMI itself as a public MCP server is a separate P2 product/security surface and is not implicitly enabled by these classes.

## 21. Deterministic acceptance

The NODE-26 test suite covers:

- current protocol constants;
- server registration SSRF checks;
- request-time DNS/IP revalidation;
- approved/enabled server requirement;
- cross-tenant server denial;
- tenant-bound credentials;
- 2026 header / `_meta` consistency;
- no modern session header;
- independent modern calls served by different instances;
- discovery metadata cache hit and tenant scoping;
- discovery cache expiry;
- no execution-result caching;
- `server/discover` + `tools/list` path;
- exact admin policy requirement for discovered tools;
- server annotations do not control LUMI risk;
- write MCP policy requires idempotency;
- NODE-25 HITL runs before MCP write;
- NODE-20-style replay executes one MCP write;
- malicious remote names rejected;
- namespace collision rejected;
- unsupported schema semantics rejected;
- `x-mcp-header` rejected;
- MRTR `input_required` fails closed with sanitized metadata;
- HTTP authentication failure normalization;
- raw JSON-RPC error sanitization;
- direct 2025 legacy initialize/session compatibility;
- legacy session state isolated from modern path.

The integration smoke additionally proves:

```text
MCP discovery
-> approved ToolDefinitions
-> Tool Gateway read execution
-> modern stateless second instance
-> Tool Gateway HITL for MCP write
-> SideEffect replay
-> Audit without MCP credential leakage
```

## 22. CI gates

NODE-26 has three sequential gates:

```text
mcp-contract
  Python 3.12 compile
  MCP architecture/security validator

mcp-security
  revalidate NODE-25 Tool Gateway contract
  all Tool Gateway/MCP deterministic tests
  MCP -> Tool Gateway integration smoke

mcp-quality
  frozen uv workspace install
  Ruff
  Pyright
```

No live MCP server or credential is required for acceptance.

No hosted PASS may be claimed until GitHub Actions actually receives a runner and executes these jobs.

## 23. Next node

After NODE-26 required gates execute green: **NODE-27 — Cost Ledger**.
