# NODE-67 — Observability, LangSmith & SRE Telemetry

> Phase: 9 Production Readiness  
> Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Priority: P0 / RELEASE BLOCKER  
> Depends on: NODE-04, NODE-12, NODE-24, NODE-27, NODE-28, NODE-50, NODE-66  
> Produces: vendor-neutral telemetry contracts、correlation propagation、safe structured logs、SLO/error-budget policy、OpenTelemetry/LangSmith production integration requirements

---

## 1. 目标

生产故障不能靠“用户截图 + 猜”。建立从 Browser/API/Graph/Agent/Tool/Model/Queue/Worker/DB 到 Artifact 的关联观测，同时控制 PII、secret、高基数和 telemetry cost。

OpenTelemetry 是 vendor-neutral instrumentation 层，统一 traces/metrics correlation；LangSmith 专注 Agent/LLM trace 与 eval，不替代基础设施可观测。业务运行不得依赖 Collector、trace backend 或 LangSmith 可用性。

当前实现已落地 correlation、安全 telemetry model、HTTP 基础 instrumentation、message propagation helper、fail-open telemetry、sampling、SLO/error-budget policy 与 dashboard/alert specification。**OpenTelemetry SDK/OTLP exporter/Collector、LangSmith adapter、生产 dashboards/alerts/synthetics 仍是 P0。**

## 2. Correlation IDs

每个用户 command 贯穿：

```text
request_id
trace_id
correlation_id
organization_id
project_id
agent_run_id
task_id
operation_id
provider_request_id
```

当前 HTTP middleware 已支持 bounded `X-Request-ID` / `X-Correlation-ID` 与 W3C `traceparent` / `tracestate` 继续传播。Canonical EventEnvelope 可继承 request/correlation/trace context，供 queue/message consumer 创建 child context。

日志不用每次全塞全部字段；业务 refs 进入 span/log 前必须经过 safe-field contract，metric labels 禁止 organization/run 等高基数维度。

## 3. Traces

目标 span hierarchy：

```text
HTTP POST agent-run
  └─ domain.create_run
  └─ langgraph.run
     └─ task.research
        └─ agent.invoke
           └─ tool.web.search
     └─ task.image
        └─ model_gateway.invoke
           └─ provider.request
```

当前 core 已定义 vendor-neutral `SpanRecord` 与 correlation context；HTTP span 是首个 producer。Graph/Agent/Tool/Model/DB 的全链 span 仍未全部接线，因此不宣称 end-to-end trace 完成。

Queue/message propagation 显式通过 canonical EventEnvelope 传递 `request_id/correlation_id/traceparent/tracestate`；worker consumer 全面接线仍是 P0。

## 4. LangSmith

目标记录：

- agent/model/tool traces；
- dataset/eval；
- prompt/agent experiments；
- latency/token。

LUMI DB 保存业务状态、成本、质量摘要与可选 LangSmith trace refs；LangSmith 不成为业务真相。

当前 `SafeLangSmithTracer` 是 fail-open Port：vendor failure 不能导致 business run 失败。生产 LangSmith/OTel adapter 与 Agent/LLM fan-out 尚未组合。

生产推荐路径：应用发标准 OTel telemetry → Collector 做 redaction/sampling/fan-out → infrastructure backend + LangSmith。应用不直接绑定单一 observability vendor。

## 5. Metrics — Golden Signals

API：

```text
request_rate
error_rate
latency p50/p95/p99
saturation
```

Agent：

```text
run_success_rate
run_duration
waiting_user_duration
task_retry_rate
resume_failure
```

AI provider：

```text
provider_success
429/5xx/timeout
latency
fallback_rate
cost
```

Queue：depth / oldest age / retry / DLQ。

Quality：constraint fail / critic score / repair success。

Business：project creation / generation / export；禁止把用户内容放进 metric label。

当前 `MetricPoint` 强制固定低基数 label allowlist；HTTP duration metric 已接入。其它生产 metric producers 仍是 P0。

## 6. Logs

Structured JSON：

```text
timestamp
level
service
environment
request/trace/run refs
event/error code
safe fields
```

禁止默认输出完整 prompt、Authorization、Cookie、token、signed URL、user file contents、reasoning。

当前 API completion logs 已走 safe JSON contract；其它服务/worker/provider/admin 尚未全面迁移。

## 7. Sampling

- errors / critical traces：100% / force sample；
- normal high-volume requests：deterministic rate sampling；
- expensive full Agent traces：按环境/privacy/cost policy；
- telemetry exporter failure：fail-open，但必须有 dropped-telemetry 指标/告警。

当前 deterministic sampler 保证 ERROR/CRITICAL/forced evidence 不会被采掉。Collector tail/adaptive sampling 与 dropped-exporter observability 仍是部署 P0。

## 8. Dashboards

至少：

```text
Platform Overview
API/SSE
Agent Runs
Model Providers
Queue/Workers
Database/Cache
Cost & Budget
Design Quality
Security/Auth
```

当前存在 vendor-neutral dashboard specification；backend/data source/query/deployed render 尚未验证。

## 9. Alerts

Page / urgent：

- API SLO breach；
- Agent run failure spike；
- all provider candidates unavailable；
- queue oldest age；
- DB connection exhaustion；
- ambiguous side effect；
- security critical；
- cost anomaly。

Ticket / non-page：低优先质量趋势。

当前 alert policy inventory 已定义，但 alert engine/routing/on-call/runbook drill 尚未部署。

## 10. SLO Baseline

首次生产目标：

```text
Core API monthly availability >= 99.9%
API read/write P95 (excluding long AI work) < 500ms target
Agent command accepted P95 < 1s target
Realtime status event delivery P95 < 2s target
No duplicate paid side effects
```

AI provider自身生成时延单独 SLO，不把长视频生成计入普通 API latency failure。

当前 SLO model/versioned policy 与 error-budget math 已实现；生产 measurement/exclusion/burn-window 校准仍待真实流量证据。

## 11. Error Budget

SLO 对应 error budget；频繁超预算时暂停非必要 feature release，优先可靠性。SLO 修改必须 versioned并有证据。

当前 core 可计算 allowed bad events / remaining budget / burn ratio；自动 release policy 与真实 on-call process 尚未组合。

## 12. Telemetry Pipeline

目标：

```text
SDK instrumentation
→ OTel Collector
→ metrics backend
→ trace backend
→ log backend
          └→ LangSmith Agent/LLM trace fan-out
```

Backend 可为 Prometheus/Grafana/Tempo/Loki 或云服务，应用代码不绑定具体 vendor。

当前仓库**没有把 OTel SDK/Collector 部署假装成已完成**：`TelemetrySink` 是 vendor-neutral Port，默认 API 只启用 safe JSON logger；`NODE67-GAP-101` 在真实 OTLP/Collector 部署前保持 OPEN。

## 13. Frontend

目标捕获：

- route errors；
- Canvas crashes；
- API failures；
- Web Vitals / interaction perf；
- correlation/request id。

用户内容、Canvas截图、Prompt、Artifact binary 不自动上报错误平台。

Frontend RUM 尚未实现/部署，保持 P0。

## 14. Synthetic Checks

目标：

```text
homepage
login test env
API health
create/read synthetic project
mock/no-cost agent path
storage roundtrip scoped
```

真实付费 AI synthetic probe 低频且必须有预算和独立 synthetic tenant。

当前 external synthetics 尚未部署。

## 15. Tests

当前 core tests覆盖：

- HTTP request/correlation/trace propagation；
- canonical event propagation / message continuation；
- malformed W3C trace rejection；
- telemetry exporter/LangSmith failure不影响业务；
- log/attribute secret与 raw-content rejection；
- metric high-cardinality guard；
- error/critical sampling；
- SLO/error-budget math；
- middleware order 与 NODE-66 response-security compatibility。

仍需真实环境：HTTP→queue→worker→provider/exporter integration、Collector outage/backpressure、dashboard query、alert firing/runbook drill、frontend RUM 与 production sampling validation。

## 16. 验收标准

- [x] HTTP correlation/request/trace context core implemented。
- [x] EventEnvelope producer propagation 与 message continuation helper implemented。
- [x] vendor-neutral telemetry contracts implemented。
- [x] telemetry / LangSmith failures fail-open，不改变业务状态。
- [x] logs/span fields有 secret/raw-content guard，metric labels有低基数 guard。
- [x] deterministic sampling 保证错误/关键证据不被采掉。
- [x] SLO / error-budget core policy与 dashboard/alert specifications已建立。
- [ ] Trace 可从 request 实际追到 Graph/Tool/Model/provider/Artifact。
- [ ] OTel SDK/OTLP exporter/Collector production operational。
- [ ] LangSmith Agent/LLM OTel fan-out 与 eval operational。
- [ ] 关键 dashboards/alerts 已部署并通过 fire/drill。
- [ ] Frontend RUM / synthetics operational。
- [ ] production telemetry retention/privacy/access/cardinality/backpressure policy完成。
- [ ] latest-head Hosted / production-like validation green。

## 17. Definition of Done

NODE-67 当前是 **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**。

```text
observability stack operational
+ request→queue→worker→provider/artifact trace correlation green
+ safe logs/metrics validated against production traffic
+ LangSmith outage does not affect business runs
+ dashboard/alert/SLO runbook drill tested
+ open P0 gap ledger = 0
```

当前 open P0 source of truth：`reports/nodes/NODE-67/gap-ledger.json`。

下一节点：NODE-68 Recovery。
