# NODE-25 — Tool Gateway

> Phase: 3 AI Infrastructure  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE / SECURITY  
> Depends on: NODE-16, NODE-20, NODE-21, NODE-12  
> Produces: Tool Registry、权限/风险/审计、Native/MCP Adapter、统一调用合同

---

## 1. 目标

所有 Agent 外部工具统一通过 Tool Gateway。工具包括 Search、Browser、Storage、数据库受控查询、媒体处理、GitHub、未来 SaaS/MCP。Agent 不拥有任意网络/数据库权限。

## 2. Tool Definition

```yaml
name: web.search
version: 1.0.0
description: Search public web
input_schema: {...}
output_schema: {...}
risk: READ_EXTERNAL
idempotency: NOT_REQUIRED
permissions:
  - tool.web.search
runtime: native|mcp|sandbox
```

## 3. Risk Tiers

```text
READ_INTERNAL
READ_EXTERNAL
WRITE_INTERNAL
WRITE_EXTERNAL
DESTRUCTIVE
FINANCIAL
PRIVILEGED
```

risk 决定 permission、HITL、audit、idempotency 和 timeout policy。

## 4. Tool Call Flow

```text
Agent
→ ToolRequest
→ Registry validation
→ permission policy
→ risk/HITL policy
→ input validation
→ side-effect/idempotency guard
→ adapter
→ output validation/normalization
→ audit/trace
→ Agent
```

## 5. Request

```text
tool_call_id
organization_id
agent_run_id
task_id
actor_agent
name/version
arguments
purpose
idempotency_key?
```

## 6. Output

大输出不得直接全塞 Agent context：

```text
summary
structured data
resource refs
truncated flag
full_result_ref
```

Context Engine 决定读取多少。

## 7. Permissions

Agent Registry 定义 allowed tool patterns；Organization policy 可进一步收窄。默认 deny。

Subagent 权限不能自动扩大父 Agent 权限。

## 8. HITL

示例：

- web.search：无需。
- read project asset：无需但 tenant guard。
- publish external：HITL。
- delete external：HITL。
- financial：HITL/专门规则。

由 LangGraph interrupt 承担等待，Tool Gateway 返回 `APPROVAL_REQUIRED` contract。

## 9. Native Tools P0

```text
web.search (adapter/mock)
web.fetch/browser-controlled
asset.read
asset.write-derived
project.query
artifact.query
sandbox.execute (through sandbox service)
media.inspect
```

不提供 unrestricted SQL tool 给普通 Agent。

## 10. Browser / SSRF

Browser/fetch tool：

- URL scheme allowlist http/https；
- DNS/IP validation；
- block loopback/link-local/private/metadata；
- redirect revalidation；
- response size/time limit；
- content type restriction；
- no ambient cookies/secrets。

## 11. Database Tool

Agent 只访问 domain query tool 或只读受控 SQL sandbox（若未来需要）。P0 禁止把生产 DB DSN 给 Agent。

## 12. Tool Versioning

Breaking input/output change → major tool version。Agent/Skill 绑定版本范围，Trace 保存 resolved exact version。

## 13. Audit

对所有 write/destructive/privileged 调用记录：

```text
who
which tool/version
scope
purpose
result
side-effect operation id
trace
```

敏感参数做 field-level redaction。

## 14. Tests

- schema validation；
- forbidden tool；
- subagent escalation；
- HITL；
- SSRF fixtures；
- oversized output；
- idempotent write；
- tool timeout；
- output schema invalid。

## 15. 验收标准

- [ ] Agent 外部能力统一走 Gateway。
- [ ] Tool Registry/版本存在。
- [ ] default deny permission。
- [ ] risk tiers 生效。
- [ ] write tool 接 SideEffect Gateway。
- [ ] SSRF 防护测试。
- [ ] large output 可 offload。

## 16. Definition of Done

```text
tool gateway implemented
+ native tools smoke green
+ permission/HITL/security suites green
```

下一节点：NODE-26 MCP Integration。
