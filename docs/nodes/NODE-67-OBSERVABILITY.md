# NODE-67 — Observability, LangSmith & SRE Telemetry

> Phase: 9 Production Readiness  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / RELEASE BLOCKER  
> Depends on: NODE-04, NODE-12, NODE-24, NODE-27, NODE-28, NODE-50  
> Produces: OpenTelemetry traces/metrics/log correlation、LangSmith Agent tracing、Dashboards/Alerts/SLO instrumentation

---

## 1. 目标

生产故障不能靠“用户截图 + 猜”。建立从Browser/API/Graph/Agent/Tool/Model/Queue/Worker/DB到Artifact的关联观测，同时控制PII和成本。

OpenTelemetry作为vendor-neutral instrumentation层，统一生成/收集/导出traces、metrics、logs；LangSmith专注Agent/LLM Trace与Eval，不替代基础设施可观测。

## 2. Correlation IDs

每个用户command贯穿：

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

日志不用每次全塞全部字段，但关键服务自动context propagation。

## 3. Traces

Span hierarchy示例：

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

Queue/message propagation显式传trace context。

## 4. LangSmith

记录：

- agent/model/tool traces；
- dataset/eval；
- prompt/agent experiments；
- latency/token。

LUMI DB保存业务状态/成本/质量摘要与LangSmith trace refs。LangSmith故障不得导致业务run失败，可buffer/drop telemetry按policy。

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

Queue：depth/oldest age/retry/DLQ。

Quality：constraint fail/critic score/repair success。

Business：project creation/generation/export，不混入PII。

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

禁止默认输出完整prompt、Authorization、signed URL、user file contents。

## 7. Sampling

- errors/critical traces high/100%采样；
- normal high-volume request按rate/adaptive sampling；
- expensive full Agent traces按环境/privacy policy。

不能为了省钱把所有失败trace采掉。

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

## 9. Alerts

Page/urgent：

- API SLO breach；
- Agent run failure spike；
- all provider candidates unavailable；
- queue oldest age；
- DB connection exhaustion；
- ambiguous side effect；
- security critical；
- cost anomaly。

Ticket/non-page：低优先质量趋势。

## 10. SLO Baseline

首次生产目标（实施阶段可用负载测试修订）：

```text
Core API monthly availability >= 99.9%
API read/write P95 (excluding long AI work) < 500ms target
Agent command accepted P95 < 1s target
Realtime status event delivery P95 < 2s target
No duplicate paid side effects
```

AI provider自身生成时延单独SLO，不把60秒生视频归API latency失败。

## 11. Error Budget

SLO对应error budget；频繁超预算时暂停非必要feature release，优先可靠性。SLO修改versioned并有证据。

## 12. Telemetry Pipeline

```text
SDK instrumentation
→ OTel Collector
→ metrics backend
→ trace backend
→ log backend
```

Backend可以Prometheus/Grafana/Tempo/Loki或云服务，应用代码不绑定具体vendor。

## 13. Frontend

捕获：

- route errors；
-Canvas crashes；
- API failures；
- Web Vitals/interaction perf；
- correlation/request id。

用户内容/Canvas截图不自动上报错误平台。

## 14. Synthetic Checks

每几分钟：

```text
homepage
login test env
API health
create/read synthetic project
mock/no-cost agent path
storage roundtrip scoped
```

真实付费AI synthetic probe低频且有预算。

## 15. Tests

- trace propagation HTTP→queue→worker；
- LangSmith outage不影响run；
- log redaction；
- alert test；
- high cardinality guard；
- dashboard data；
- telemetry sampling。

## 16. 验收标准

- [ ] Trace可从request追到provider/artifact。
- [ ] OTel vendor-neutral。
- [ ] LangSmith与业务observability分工明确。
- [ ] 关键dashboards/alerts工作。
- [ ] logs无secrets/prompt默认泄漏。
- [ ] SLO与error budget发布。

## 17. Definition of Done

```text
observability stack operational
+ trace/log/metric correlation green
+ alert/SLO runbook tested
```

下一节点：NODE-68 Recovery。
