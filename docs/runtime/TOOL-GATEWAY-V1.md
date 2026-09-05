# Tool Gateway V1

> NODE-25 runtime/security contract.  
> Depends on NODE-16 Authentication & Tenant Isolation, NODE-20 Idempotency & Side Effect Gateway, NODE-21 Sandbox Runtime, and NODE-18 Asset Storage.

## 1. Responsibility

Tool Gateway is the single policy and execution boundary for Agent access to external or privileged capabilities.

Agents do **not** receive ambient:

- arbitrary network access;
- production database credentials;
- object-storage credentials;
- Docker socket access;
- provider API keys;
- unrestricted host shell access.

The execution flow is fixed:

```text
Agent
  -> ToolRequest
  -> exact Tool Registry resolution
  -> tenant/tool permission policy
  -> input schema validation
  -> risk / HITL policy
  -> idempotency + SideEffect guard for writes
  -> Native / Sandbox / future MCP adapter
  -> output schema validation
  -> result-size policy / offload
  -> redacted Audit
  -> ToolResult
```

No adapter may execute before permission, schema, and approval gates finish.

## 2. Tool definition

Every tool is versioned independently:

```text
name
version
input_schema
output_schema
risk
idempotency
permissions
runtime
timeout_seconds
max_inline_output_bytes
sensitive_fields
enabled
```

Tool names are stable dotted identifiers such as `web.search` or `asset.read`.

Breaking request/response changes require a new major version. Runtime resolution accepts an exact version or a major constraint such as `1.x`, while every `ToolResult` and Audit record stores the exact resolved version.

## 3. Frozen risk vocabulary

NODE-25 freezes:

```text
READ_INTERNAL
READ_EXTERNAL
WRITE_INTERNAL
WRITE_EXTERNAL
DESTRUCTIVE
FINANCIAL
PRIVILEGED
```

Write-class risks are:

```text
WRITE_INTERNAL
WRITE_EXTERNAL
DESTRUCTIVE
FINANCIAL
PRIVILEGED
```

A write-class `ToolDefinition` cannot be constructed with `idempotency=NOT_REQUIRED`. This prevents a later catalog edit from silently bypassing NODE-20.

## 4. Permission model

Permission is an intersection, not a union.

A call must satisfy all applicable layers:

```text
authenticated tenant context
AND organization tool policy
AND Agent allow patterns
AND parent Agent allow patterns when this is a subagent
AND required tool permission scopes
```

Organization deny has priority over allow.

`agent_allow_patterns=()` is valid and means **deny every tool**.

Parent scope uses explicit semantics:

```text
parent_allow_patterns = None  -> root Agent, no parent layer
parent_allow_patterns = ()    -> subagent whose parent granted zero tools
parent_allow_patterns = (...) -> subagent may only use the intersection
```

Therefore an empty parent scope cannot accidentally mean unrestricted access.

## 5. NODE-16 boundary

NODE-16 remains authoritative for user/session identity, organization membership, tenant authorization, and RBAC.

Tool Gateway receives an already authenticated organization context and a derived tool-scope snapshot. It does not copy password/session/membership logic.

The request organization must equal the permission-context organization. A mismatch fails at contract construction.

P0 tool scopes use names such as:

```text
tool.web.search
tool.web.fetch
tool.asset.read
tool.asset.write-derived
tool.project.query
tool.artifact.query
tool.sandbox.execute
tool.media.inspect
```

A future Agent Registry can persist which patterns each Agent role is allowed to request; Tool Gateway continues to enforce the resulting snapshot.

## 6. HITL contract

Default NODE-25 approval policy requires HITL for:

```text
WRITE_EXTERNAL
DESTRUCTIVE
FINANCIAL
PRIVILEGED
```

`WRITE_INTERNAL` is still idempotency-protected but does not automatically require human approval.

When approval is needed and no valid approval is resolved, Tool Gateway returns:

```text
status = APPROVAL_REQUIRED
approval_id?
error_code = TOOL_APPROVAL_REQUIRED
```

No adapter or side-effect guard executes before approval.

Tool Gateway never treats the mere presence of `approval_token` as approval. The injected `ApprovalResolver` must validate the token/decision against the full request. A production approval should bind at least:

```text
organization_id
agent_run_id
tool name + exact version
canonical argument identity / scope
purpose or approved action class
expiry
approver identity
```

This keeps LangGraph interrupt/resume or a later approval service outside the tool package while preserving a narrow contract.

## 7. NODE-20 SideEffect Gateway boundary

Every write tool requires:

```text
idempotency = REQUIRED
ToolRequest.idempotency_key
SideEffectGuard implementation
```

Tool Gateway converts a call into `ToolSideEffectContext`:

```text
organization_id
operation_type = tool:<name>:<version>
idempotency_key
business_scope_id = task_id
request = {
  tool,
  agent_run_id,
  task_id,
  arguments,
  purpose
}
```

The production composition root maps this into NODE-20 `IdempotencyContext` and delegates execution to NODE-20 `SideEffectGateway`.

Expected NODE-20 behavior remains authoritative:

```text
EXECUTE
REPLAY
WAIT
RECONCILE
RETRY_SAFE
FINAL_FAILURE
AMBIGUOUS
```

Tool Gateway does not reimplement leases, provider reconciliation, or durable idempotency storage.

The deterministic NODE-25 test guard exists only to prove the interface and replay semantics without requiring PostgreSQL in the stdlib contract gate.

## 8. P0 tool catalog

NODE-25 freezes eight initial definitions:

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

There is intentionally no unrestricted SQL tool.

`project.query` is a domain-query adapter boundary. Approved query names are resolved by trusted application code; an Agent never receives a production DSN.

## 9. Native adapter boundary

`NativeFunctionAdapter` wraps a trusted application function behind the same ToolDefinition contract.

Native functions remain responsible for resource-specific tenant checks such as:

```text
asset belongs to organization
project belongs to organization
artifact belongs to organization
resource is in an allowed lifecycle state
```

Tool permission does not replace repository-level tenant guards.

## 10. Web search

`WebSearchAdapter` consumes a narrow `SearchBackend` port and returns normalized:

```text
title
url
snippet
```

Provider credentials, if a production search backend needs them, are owned by the trusted adapter/composition layer and are not fields in `ToolRequest`.

## 11. Web fetch / SSRF boundary

`SafeWebFetchAdapter` only permits HTTP/HTTPS and uses `SSRFPolicy` before every network hop.

The validator rejects:

```text
userinfo in URL
fragment-bearing target URLs
unsupported schemes
non-80/443 ports in P0
localhost aliases
Docker host aliases
metadata host aliases
.loopback
.private/RFC1918
.link-local
.multicast
.reserved
.unspecified
non-global IPv4/IPv6
```

DNS resolution is fail-closed: if **any** returned address is unsafe, the target is rejected.

### DNS rebinding rule

Validation alone is not enough if the HTTP client later performs a second DNS lookup.

NODE-25 therefore passes a validated `resolved_ip` to the `PinnedHTTPTransport` contract:

```text
validated hostname
validated/pinned IP
original URL
Host value / TLS hostname context
timeout
max bytes
fixed headers
```

A production transport must connect to the validated IP rather than silently resolving the hostname again. For HTTPS it must still validate the certificate for the original hostname/SNI.

### Redirect rule

Redirects are not automatically trusted.

Every `Location` is resolved against the current URL and then fed through the full SSRF validator before another transport call. Thus:

```text
https://public.example
  -> 302 http://169.254.169.254/latest/meta-data
```

is blocked before the second fetch.

### Ambient authority

The reference adapter sends fixed `Accept` and `User-Agent` headers only. It does not inject Authorization or Cookie headers.

Production transport implementations must also disable ambient environment-proxy behavior unless a separately controlled egress proxy is intentionally part of the security design.

### Response limits

P0 enforces:

```text
bounded timeout
bounded response bytes
bounded redirect count
allowlisted text/JSON content types
```

Binary downloads should use a dedicated Asset ingestion path rather than bypassing NODE-18 validation through `web.fetch`.

## 12. NODE-21 Sandbox boundary

`sandbox.execute` does not run `subprocess`, shell commands, or Docker in Tool Gateway.

`SandboxExecuteAdapter` calls a narrow `SandboxExecutor` service port and passes:

```text
organization_id
agent_run_id
task_id
argv list
timeout
```

The production implementation must delegate to NODE-21 `SandboxBackend` / sandbox service, where filesystem, PID, memory, CPU, timeout, and network isolation are enforced.

A string shell command is not accepted by the adapter; the command is an argv list.

## 13. NODE-18 Asset and result offload boundary

Large tool output must not be copied wholesale into Agent context.

Each ToolDefinition sets `max_inline_output_bytes`. Tool Gateway canonicalizes validated JSON output and compares its byte size.

If it exceeds the limit:

```text
ResultOffloader.store(...)
-> full_result_ref
ToolResult.truncated = true
ToolResult.data = bounded preview
```

Production `ResultOffloader` should store the full payload through the trusted Object Storage / Artifact boundary from NODE-18, with organization scoping and an opaque resource reference.

The Tool package itself carries no object-storage key.

## 14. Input and output validation

NODE-25 includes a deterministic stdlib JSON-schema subset for P0 contracts:

```text
type
const
enum
properties
required
additionalProperties
min/max properties
items
min/max items
min/max string length
minimum/maximum number
```

Input validation happens before approval/adapter execution. Output validation happens immediately after adapter/SideEffect execution and before returning or offloading.

Provider-native or malformed output therefore cannot silently become trusted Agent context.

Full production JSON Schema support may replace the implementation behind the same validator port later if required.

## 15. JSON and binary boundary

ToolRequest/ToolResult structured data are JSON-like.

The canonical contract rejects:

```text
bytes / bytearray / memoryview
non-finite floats
non-string object keys
excessive nesting
```

Large/binary objects belong in Asset/Object Storage and are referenced by opaque IDs.

## 16. Audit

Successful, denied, approval-required, validation, timeout, and adapter failure paths emit structured audit evidence once a tool definition is resolved.

Audit fields include:

```text
tool_call_id
organization_id
actor_id
actor_agent
resolved exact tool/version
risk
purpose
status
trace_id
redacted arguments
replayed
side_effect_operation_id
approval_id
error_code
```

Audit does not record adapter output bodies.

Secret-like argument fields are recursively redacted, including keys containing forms of:

```text
password
secret
token
api_key
authorization
cookie
credential
```

ToolDefinition can add explicit sensitive field paths.

## 17. Failure semantics

Examples:

```text
TOOL_NOT_FOUND
TOOL_VERSION_NOT_FOUND
TOOL_DISABLED
TOOL_PERMISSION_DENIED
TOOL_INPUT_SCHEMA_INVALID
TOOL_APPROVAL_REQUIRED
TOOL_APPROVAL_DENIED
TOOL_IDEMPOTENCY_KEY_REQUIRED
TOOL_SIDE_EFFECT_GUARD_REQUIRED
TOOL_TIMEOUT
TOOL_ADAPTER_EXECUTION_ERROR
TOOL_OUTPUT_SCHEMA_INVALID
TOOL_OUTPUT_OFFLOAD_REQUIRED
TOOL_SSRF_BLOCKED
TOOL_REDIRECT_LIMIT
TOOL_RESPONSE_TOO_LARGE
TOOL_CONTENT_TYPE_NOT_ALLOWED
```

Unexpected adapter exceptions are normalized and do not place the raw exception message into Audit.

## 18. Package privilege boundary

`services/tool-gateway` deliberately keeps `dependencies = []` for NODE-25.

The static architecture validator rejects direct imports of privileged implementation libraries such as:

```text
asyncpg
SQLAlchemy
boto3
Docker SDK
subprocess
psycopg
```

It also rejects ambient secrets/DSN markers and Docker socket references in Tool Gateway source.

This is an architecture gate, not a claim that these libraries can never exist elsewhere in LUMI. They belong behind trusted ports in the owning service.

## 19. Deterministic acceptance

The stdlib unit/security suite covers:

- Tool Registry exact and major-version resolution;
- schema validation before execution;
- empty Agent allowlist default deny;
- forbidden tool pattern;
- subagent parent-scope escalation;
- empty parent scope = no tools;
- HITL before side effects;
- write idempotency key required;
- SideEffect guard required;
- duplicate write replay invokes adapter once;
- output schema rejection;
- timeout normalization;
- adapter exception normalization/audit;
- secret field redaction;
- large output offload;
- direct loopback/private/link-local/metadata SSRF rejection;
- mixed safe+unsafe DNS answer rejection;
- redirect SSRF revalidation;
- validated IP pin passed to transport;
- no ambient Authorization/Cookie headers;
- content type and response-size restriction;
- P0 catalog contains exactly eight tools;
- Search adapter normalization;
- Sandbox adapter uses isolated service port and argv contract.

The deterministic integration smoke composes Registry, permission, Search, Safe Fetch, project query, Asset write, Sandbox execute, SideEffect replay, offload, Audit, subagent denial, and redirect-to-metadata rejection without live external credentials.

## 20. CI gates

NODE-25 workflow is layered:

```text
tool-contract
  -> compile + architecture/security contract

tool-security
  -> upstream NODE-20/NODE-21 static boundary checks
  -> all Tool Gateway unit/security tests
  -> deterministic integration

tool-quality
  -> frozen uv workspace install
  -> Ruff
  -> Pyright
```

No hosted PASS is claimed until GitHub Actions actually receives a runner and executes these gates.

## 21. Production follow-ups

NODE-25 intentionally leaves these behind stable ports for subsequent nodes:

- durable Agent tool-policy control plane;
- approval persistence/UI;
- production Search provider adapter;
- pinned HTTP transport implementation;
- NODE-20 production `SideEffectGuard` composition adapter;
- NODE-18 production result offloader;
- remote NODE-21 sandbox service client;
- shared metrics/rate limiting;
- MCP adapters.

NODE-26 adds MCP Integration without weakening the NODE-25 permission/risk/idempotency/audit pipeline.

## 22. Next node

After NODE-25 required gates execute green: **NODE-26 — MCP Integration**.
