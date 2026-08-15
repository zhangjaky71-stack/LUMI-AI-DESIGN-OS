# NODE-69 — Performance, Load & Scalability Validation

> Phase: 9 Production Readiness  
> Status: SOURCE IMPLEMENTED / RELEASE BLOCKED  
> Priority: P0 / RELEASE BLOCKER  
> Depends on: NODE-40, NODE-55, NODE-67, NODE-68  
> Produces: Load profiles、API/DB/Queue/Canvas/Agent并发测试、容量模型与Scaling Policy

---

## 0. Implementation Status — 2026-08-15

Source baseline 已实现：

- `perf/profiles/v1/` A–G 版本化 workload profiles；
- G = 100 connected users / 20 concurrent AI generations / 10 media jobs / 120 SSE；
- canonical workload 100% deterministic mock / 0% real provider；
- `perf/budgets/v1.json` 只定义 target，明确 `measured=false`；
- result evidence schema 强制 HTTP/resource/DB/Queue/AI latency decomposition；
- dependency-free performance contract validator；
- loopback deterministic Mock Provider；
- guarded HTTP load runner（远端必须显式 enable + hostname ACK，禁止 redirect）；
- absolute + baseline regression evaluator；
- read-only PostgreSQL performance snapshot；
- Capacity/Autoscaling Plan；
- PR source Performance Contract + manual deterministic smoke artifact workflow。

**Release 验收尚未完成**：没有 production-like Profile G、Canvas reference-device、multi-hour soak、failure-under-load、measured safe concurrency/cost 数据。因此第 17 节保持未勾选。

Release Evidence：`docs/release-evidence/NODE-69-PERFORMANCE-RELEASE-EVIDENCE.md`。

## 1. 目标

用测量证明系统在预期首发负载下不会因API、数据库、队列、Canvas或provider并发崩溃，并建立“什么时候扩容”的容量模型。

## 2. Workload Model

先定义用户行为而非盲打QPS：

```text
browse projects/assets
open workspace + SSE
canvas save operations
start agent runs
image generations
video jobs
asset upload/export
team comments
```

版本化 A–G profiles 覆盖 read-heavy、write-heavy、AI burst、long generation、asset upload、large Canvas 和 mixed launch traffic。大量模型负载使用 deterministic Mock Provider；真实 provider 比例必须显式声明并受预算控制。

## 3. API Targets

当前 source target（不是实测结果）：

```text
cached/metadata API P95 < 300ms
ordinary API P95 < 800ms
enqueue endpoint P95 < 500ms
SSE platform propagation P95 < 1s (exclude provider time)
common local interaction P95 < 100ms
```

实际 release 阈值在 Staging 报告结合产品体验与容量数据冻结。

## 4. Database

测试：

- project/artifact/task lists；
- tenant filters；
- task scheduler `SKIP LOCKED`；
- outbox dispatcher；
- cost reservation contention；
- version head optimistic lock。

使用 `pg_stat_statements` / EXPLAIN ANALYZE / slow query、locks、pool saturation；禁止靠无限提高DB规格掩盖N+1。NODE-69 提供 read-only snapshot，不会为了性能采集自动修改数据库扩展。

## 5. Queue

测：

```text
jobs/sec
oldest age
worker concurrency
retry storm
provider slow responses
video/media queue isolation
```

关键queue设置autoscale/alert threshold。

## 6. Agent Concurrency

模型/provider限制通常成为瓶颈。测：

- concurrent runs；
- Tool Gateway；
- Model Gateway rate-limits；
- context assembly；
- checkpointer；
- streaming connections。

通过semaphore/tenant fairness避免一个org占满全局。Provider latency 必须与 LUMI platform overhead 分开记录。

## 7. Canvas

浏览器基准覆盖：

```text
500 nodes
1000 nodes
image-heavy 1000 nodes
multi-page
long session
stress extensions toward 2k/10k as product data model supports
```

收集 FPS/frame/long tasks、memory、load/save/zoom/pan/interaction、Web Vitals。Reference device/browser 必须随结果冻结；没有 reference-device run 不得宣称 Canvas target 达标。

## 8. Assets

大文件直传；测试multipart、concurrent thumbnail、CDN/cache。API memory不能随upload size线性增长。

## 9. Export / Media

分离resource pools；4K export/video不能拖垮API/Agent。Worker CPU/memory限额和queue isolation实测。现有 Media Worker 已使用独立 routing queues，但“隔离有效”仍需 Profile G/Media 压测数据证明。

## 10. Cache

明确cache hit ratio；cache invalidation按version。禁止通过cache返回跨tenant数据。Redis不可用时核心读取可降级DB，性能下降但correctness保持。

## 11. CDN

Production静态Web和授权资产preview采用CDN策略；private assets使用signed/cookie策略并避免长期public URL。

## 12. Autoscaling Signals

```text
API: p95 latency + inflight + CPU + DB pool
Agent: queue depth + oldest age + active tasks + CPU
Tool: queue depth + oldest age + active tasks + errors
Media: queue depth + oldest job + CPU + memory
SSE: connections + event backlog + propagation latency
DB: connections + IO + query latency + lock/wait pressure
```

不要只按CPU扩Agent/Media worker，因为外部wait或队列积压时CPU可能很低。

## 13. Load Tools

NODE-69 当前提供 stdlib deterministic mock、guarded HTTP runner、regression evaluator 和 DB snapshot，避免引入新的锁文件依赖。脚本版本化到 `perf/` / `scripts/`。AI live load必须显式批准与预算上限；PR CI 禁止真实 provider。

## 14. Soak Test

至少数小时的Staging soak：监测 API RSS、worker N jobs、connection leak、Canvas open/close/generate cycles、Blob URL/SSE/Pixi texture/listener/AbortController 等长期资源增长。

## 15. Failure Under Load

在压力中模拟：

- provider 429；
- worker restart；
- Redis latency；
- DB failover staging-equivalent；
- SSE reconnect storm。

## 16. Capacity Report

`docs/performance/NODE-69-CAPACITY-PLAN.md` 已定义结构和 autoscaling signals；safe concurrency 数字保持 **PENDING**，直到实际 benchmark 填充：

```text
load profile
max tested concurrency
bottleneck
resource utilization
cost/hour estimate
scaling threshold
known limit
```

Provider variable cost 与 platform infrastructure cost 分开。

## 17. 验收标准

- [ ] Launch target负载通过。
- [ ] API/SSE/DB/Queue/Canvas都有数据。
- [ ] media workload隔离。
- [ ] 无明显memory/connection leak。
- [ ] autoscaling信号定义并由运行数据校准。
- [ ] capacity/cost报告由测量数据完成。

## 18. Definition of Done

```text
performance suite versioned
+ launch target green
+ soak/failure-under-load green
+ capacity model published with measured values
```

下一节点：NODE-70 AI Regression。
