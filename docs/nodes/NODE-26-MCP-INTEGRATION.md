# NODE-26 — MCP Integration

> Phase: 3 AI Infrastructure  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-25  
> Produces: MCP client adapter、server registry、2026-07-28 协议兼容策略、授权/信任边界

---

## 1. 目标

让 Tool Gateway 可接入标准 MCP Server，同时不把 MCP server 自动视为可信。MCP 是 transport/integration protocol，不替代 LUMI 的 permission、audit、tenant、HITL 和 side-effect policies。

## 2. Protocol Baseline

实施基线以 MCP `2026-07-28` 规范为首选：其核心是 stateless request/response，取消旧式强 session handshake，并引入 header-based routing、cacheable list results、授权强化及 extensions。

如果生态 server 暂时停留旧协议，兼容层必须隔离在 adapter，不影响 Tool Gateway domain contract。

## 3. MCP Placement

```text
Agent
→ Tool Gateway
→ MCP Adapter/Policy
→ MCP Server
```

禁止：

```text
Agent → arbitrary MCP server URL
```

## 4. Server Registry

```text
server_id
name
base_url/transport
enabled
trust_level
organization_scope/global
allowed_tool_patterns
protocol_versions
auth_profile
network_policy
last_discovered_at
```

只有管理员批准的 server 可启用。

## 5. Discovery

新规范下 discovery 可选；LUMI 支持：

- explicit configured catalog；
- `server/discover`（支持时）；
- tool list cache hints。

发现的新工具不是自动授权，先进入 registry/policy validation。

## 6. Header Routing

Gateway proxy 可利用：

```text
MCP-Protocol-Version
Mcp-Method
Mcp-Name
```

执行路由、policy 和审计，但仍验证 JSON-RPC body 一致性，不能只信 header。

## 7. Authentication

MCP server credential 由 Tool Gateway Secret Manager 持有；不传给 Agent。

支持 OAuth/enterprise authorization 时，token scope 与 tenant/user 映射明确。禁止跨组织复用用户级 delegated token。

## 8. Tool Mapping

MCP tool schema → LUMI ToolDefinition adapter：

- JSON Schema validation；
- namespacing `mcp.<server>.<tool>`；
- risk classification；
- output size policy；
- write detection 不只依赖 server description，需要 admin policy。

## 9. Multi Round-Trip / Extensions

对需要 MRTR 或扩展的 server：由 MCP Adapter 协调，不允许 server 直接向最终用户任意请求敏感信息。任何 elicitation/sampling 类行为映射到 LUMI policy/HITL。

## 10. Network Security

MCP server URL 只能来自 registry，创建/更新时做 SSRF 校验。Runtime egress allowlist；禁止 metadata/internal pivot。

## 11. Cache

Tool list/resource metadata 可按规范 cache hints 缓存；tool execution result 只有明确 safe/cacheable 才缓存，write tool 禁止误缓存。

## 12. Failure

统一错误：

```text
MCP_SERVER_UNAVAILABLE
MCP_PROTOCOL_MISMATCH
MCP_TOOL_NOT_FOUND
MCP_SCHEMA_INVALID
MCP_AUTH_FAILED
MCP_POLICY_DENIED
```

不把 raw JSON-RPC error 直接泄露 UI。

## 13. Compatibility Tests

- 2026-07-28 mock server；
- older compatible adapter fixture；
- no-session multiple instances；
- discovery cache；
- auth failure；
- malicious tool schema/name；
- unapproved tool；
- MRTR approval bridge（如实现）。

## 14. Public MCP Server

LUMI 对外提供 MCP server 属 P2（NODE roadmap 后段），本节点只设计 internal client side。不得为了“支持 MCP”扩大 P0 scope。

## 15. 验收标准

- [ ] MCP server 必须 registry 批准。
- [ ] 2026-07-28 client path 可测试。
- [ ] MCP tool 映射到 LUMI Tool Policy。
- [ ] credentials 不给 Agent。
- [ ] SSRF/permission 生效。
- [ ] 老协议兼容隔离在 adapter。

## 16. Definition of Done

```text
MCP adapter implemented
+ mock MCP integration green
+ registry/policy/security tests green
```

下一节点：NODE-27 Cost Ledger。
