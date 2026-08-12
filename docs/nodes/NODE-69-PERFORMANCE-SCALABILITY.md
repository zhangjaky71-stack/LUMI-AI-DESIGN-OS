# NODE-69 — Performance, Load & Scalability Validation

> Phase: 9 Production Readiness  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / RELEASE BLOCKER  
> Depends on: NODE-40, NODE-55, NODE-67, NODE-68  
> Produces: Load profiles、API/DB/Queue/Canvas/Agent并发测试、容量模型与Scaling Policy

---

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

至少三个profile：DEV、STAGING_TARGET、PROD_LAUNCH_TARGET。

## 3. API Targets

不含外部AI长任务的业务API目标：

```text
read P95 < 300-500ms target
write P95 < 500ms target
error rate < 1% under target load
agent-run accept P95 < 1s
SSE connection stability
```

实际阈值在Staging报告冻结。

## 4. Database

测试：

- project/artifact/task lists；
- tenant filters；
- task scheduler `SKIP LOCKED`；
- outbox dispatcher；
- cost reservation contention；
- version head optimistic lock。

使用EXPLAIN/slow query，禁止靠无限提高DB规格掩盖N+1。

## 5. Queue

测：

```text
jobs/sec
oldest age
worker concurrency
retry storm
provider slow responses
video queue isolation
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

通过semaphore/tenant fairness避免一个org占满全局。

## 7. Canvas

浏览器基准：

```text
2k mixed nodes normal workflow
10k stress
1k thumbnails
100 rich text
500 selected drag stress
```

收集frame time、memory、GPU texture、load time、save time。

## 8. Assets

大文件直传；测试multipart、concurrent thumbnail、CDN/cache。API memory不能随upload size线性增长。

## 9. Export / Media

分离resource pools；4K export/video不能拖垮API/Agent。Worker CPU/memory限额和queue isolation实测。

## 10. Cache

明确cache hit ratio；cache invalidation按version。禁止通过cache返回跨tenant数据。Redis不可用时核心读取可降级DB，性能下降但correctness保持。

## 11. CDN

Production静态Web和授权资产preview采用CDN策略；private assets使用signed/cookie策略并避免长期public URL。

## 12. Autoscaling Signals

```text
API CPU/request concurrency
Agent pending runs/queue age
Media queue depth/age
SSE connections
DB connections/CPU
```

不要只按CPU扩Agent worker，因为外部wait可能CPU很低但queue很高。

## 13. Load Tools

可用k6/Locust/Playwright perf等，脚本版本化到 `perf/`。AI live load有预算上限；大量模型测试使用MockProvider latency/error simulation。

## 14. Soak Test

至少数小时的Staging soak：监测memory leak、connection leak、texture/browser long-session、queue backlog。

## 15. Failure Under Load

在压力中模拟：

- provider 429；
- worker restart；
- Redis latency；
- DB failover staging-equivalent；
- SSE reconnect storm。

## 16. Capacity Report

输出：

```text
load profile
max tested concurrency
bottleneck
resource utilization
cost/hour estimate
scaling threshold
known limit
```

## 17. 验收标准

- [ ] Launch target负载通过。
- [ ] API/SSE/DB/Queue/Canvas都有数据。
- [ ] media workload隔离。
- [ ] 无明显memory/connection leak。
- [ ] autoscaling信号定义。
- [ ] capacity/cost报告完成。

## 18. Definition of Done

```text
performance suite versioned
+ launch target green
+ soak/failure-under-load green
+ capacity model published
```

下一节点：NODE-70 AI Regression。
