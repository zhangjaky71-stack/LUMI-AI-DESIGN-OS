# Tool Gateway Integration V1

> NODE-25 active-chain integration mapping.  
> This document complements `TOOL-GATEWAY-V1.md` and records which upstream node owns each correctness boundary.

## 1. Authority boundary

Agent code never receives ambient database, object-store, provider, Docker, shell, or unrestricted network credentials.

```text
Agent / Subagent
  -> ToolGatewayClient
  -> Tool Gateway
       Registry/version
       permission intersection
       risk/HITL
       schema validation
       NODE-20 side-effect port for writes
       Native / Sandbox / future MCP adapter
       result normalization/offload
       redacted audit
```

## 2. Cross-node ownership

| Concern | Owner | NODE-25 relationship |
|---|---|---|
| authenticated identity / org membership | NODE-16 | consume an already authenticated tenant/tool-scope snapshot |
| Asset/Object storage | NODE-18 | use trusted domain/offloader ports; no storage credential in Agent/tool core |
| durable side-effect replay/conflict/recovery | NODE-20 | `SideEffectGuard` maps write-class calls to `SideEffectGateway` |
| isolated process/filesystem/network execution | NODE-21 | `SandboxExecuteAdapter` calls a narrow `SandboxExecutor` service port |
| event envelope | NODE-12 | later durable tool-call event publication must use frozen event envelope contracts |
| MCP | NODE-26 | `ToolRuntime.MCP` exists, adapter activation is intentionally deferred |
| LangGraph interrupt/resume | NODE-28 | Tool Gateway returns `APPROVAL_REQUIRED`; graph owns durable wait/resume |
| approval governance | NODE-62 | approval policy/decision persistence and workflow governance |
| audit retention / legal hold | NODE-65 | Tool Gateway produces redacted structured evidence; durable governance lives there |

## 3. NODE-20 mapping

For every write-class Tool Definition:

```text
operation_type = tool:<name>:<exact-semver>
idempotency_key <= 255 chars
business_scope_id = task_id
request_hash = canonical semantic request hash
side_effect_kind = external_tool_write
```

`ToolDefinition` rejects an operation identity longer than NODE-20's 100-character contract. `ToolRequest` uses the same 255-character key maximum as `OperationRequest`.

The deterministic active-chain bridge in `tools/node25/test_node20_side_effect_bridge.py` composes the current `SideEffectGateway` and `MemoryIdempotencyStore` and proves:

- first write executes exactly once;
- duplicate semantic write replays without a second adapter invocation;
- same organization/operation/key with different semantic arguments conflicts;
- the NODE-20 conflict maps to stable Tool Gateway error `TOOL_IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST`.

Production PostgreSQL wiring remains a composition-root concern; Tool Gateway core deliberately does not import asyncpg/SQLAlchemy.

## 4. Permission intersection

Authorization is default deny and cannot be widened by subagents.

A tool must simultaneously pass:

1. Organization deny list.
2. Organization allow list when configured.
3. Agent Registry allow patterns.
4. Parent Agent allow patterns for subagents.
5. Required permission scopes from the resolved exact Tool Definition.

`parent_allow_patterns=None` means a root Agent has no parent narrowing layer. `parent_allow_patterns=()` means the parent granted zero tools, therefore the subagent has zero tools.

NODE-16 remains the source of authenticated principal/tenant identity. NODE-25 does not create a second session/RBAC system.

## 5. HITL ordering

Write/external/destructive/financial/privileged execution must never happen before required approval.

Current ordering is:

```text
Registry resolve
-> permission
-> input schema
-> write AuditSink required
-> HITL decision
-> SideEffectGuard
-> adapter
-> output schema
-> normalize/offload
-> audit
```

An approval token string alone is not authorization. An injected resolver must bind an approval decision to the tool request and scope.

## 6. Audit fail-closed rule

Read-class tools may use a Null sink in local/test composition. Write-class tools may not.

If a write-class call has no AuditSink, Tool Gateway raises:

```text
TOOL_AUDIT_SINK_REQUIRED
```

before approval resolution, SideEffectGuard entry, or adapter execution.

Audit records carry IDs, resolved tool/version, risk, purpose, trace/replay/operation/approval/error fields and redacted arguments. Adapter output bodies and raw exception strings are not copied into the audit record.

## 7. Browser / fetch safety

`web.fetch` uses a two-part contract:

- `SSRFPolicy` resolves and validates every DNS answer;
- `PinnedHTTPTransport` must connect to the already validated IP rather than silently re-resolve the hostname.

The policy blocks loopback, private, link-local, multicast, reserved, unspecified, metadata and Docker-host aliases; only HTTP/HTTPS and configured ports are allowed. Every redirect target is revalidated before a second transport call. Fixed public request headers contain no ambient Authorization or Cookie data.

A production TLS/SNI-aware pinned transport is intentionally not activated in NODE-25 until its implementation can preserve both hostname certificate verification and IP pinning without DNS rebinding.

## 8. Sandbox safety

`sandbox.execute` accepts argv only and forwards tenant/run/task identity plus timeout to a `SandboxExecutor` port. Tool Gateway contains no `subprocess`, Docker SDK, Docker socket, or host-shell execution path.

NODE-21 remains responsible for runtime image policy, filesystem/network isolation, resource limits, cancellation, output staging and cleanup.

## 9. Large results

Results exceeding `max_inline_output_bytes` cannot be returned wholesale to Agent context.

The Gateway requires `ResultOffloader`, emits a bounded preview and returns an opaque `full_result_ref`. Production binding must use NODE-18 trusted storage/Artifact boundaries; binary/object-store credentials are not allowed in Tool Gateway core.

## 10. P0 catalog

Exactly eight native/service-facing definitions are frozen for NODE-25:

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

There is no unrestricted SQL tool.

## 11. Production gaps

The exact unresolved work is tracked in `reports/nodes/NODE-25/gap-ledger.json`. No gap permits bypassing Tool Gateway; missing production bindings must fail closed or remain unavailable rather than granting Agent ambient authority.
