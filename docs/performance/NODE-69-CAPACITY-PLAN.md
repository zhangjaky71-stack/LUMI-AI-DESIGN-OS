# NODE-69 — Capacity & Autoscaling Plan

> Status: SOURCE BASELINE / CAPACITY NUMBERS PENDING MEASUREMENT  
> Profile set: `node69-launch-v1`

## Scaling principle

No production component scales from CPU alone. Scale decisions combine service pressure, latency/age and resource saturation. Paid-provider latency/capacity is tracked separately from LUMI platform capacity.

## Current release IaC mode — fail closed before measurement

Until production-like Profile G produces measured safe concurrency **and** the selected scale signal has a production emitter, Staging and Production run exact fixed ECS capacity:

- `autoscaling_enabled = false` for all seven ECS services;
- `desired_count == min_capacity == max_capacity` per service;
- no unproven `LUMI/Capacity` custom metric name or target is declared by the environment;
- Terraform owns `desired_count` and does not ignore replica-count drift;
- App Auto Scaling target-tracking resources are created only from the gated `autoscaled_services` set, which the current release contract requires to remain empty.

This is not a claim that fixed capacity is sufficient for launch. It prevents Terraform from pretending that a queue/concurrency metric exists before NODE-69 has measured the threshold and a real emitter has been deployed. Enabling dynamic scaling is a future release-contract change that must carry Profile G/component evidence plus an executable metric-emitter contract.

| Component | Baseline instance | Safe concurrency | Primary bottleneck | Scale signal |
|---|---|---|---|---|
| API | NODE-72 deployment size TBD | **PENDING load evidence** | event loop / DB pool / CPU | p95 latency + inflight + CPU + DB-pool pressure |
| Agent runtime | NODE-72 size TBD | **PENDING** | active runs / provider waits | queue depth + oldest age + active tasks + CPU |
| Tool worker | NODE-72 size TBD | **PENDING** | external I/O / sandbox/tool limits | queue depth + oldest age + active tasks + error rate |
| Media worker | separate pool required | **PENDING** | CPU/RAM/codec | media queue depth + oldest job age + CPU + memory |
| SSE tier | deployment topology TBD | **PENDING** | open sockets / event backlog | connections + event backlog + propagation p95 |
| PostgreSQL | NODE-72 managed/self-hosted choice TBD | **PENDING** | connections / IO / slow queries | connections + IO + query p95 + lock/wait pressure |
| Object storage/CDN | provider TBD | **PENDING** | bandwidth/cache miss | origin latency + errors + egress/cache hit |

## Launch profile

Profile G is the first release-capacity target:

```text
100 connected users
20 concurrent AI generations (deterministic mock for baseline)
10 concurrent media jobs
120 SSE connections
mixed read/write/asset/AI traffic
```

Passing smaller smoke tests does not satisfy launch capacity.

## Pool isolation

- API must not execute CPU-heavy media transforms synchronously.
- Media routing/worker pool scales independently from Agent/Tool/API.
- Queue age is a first-class signal; a low CPU worker with an old backlog is still under-provisioned.
- Provider-waiting work must not consume scarce CPU concurrency as if it were active compute.

## Required evidence before filling safe concurrency

For each component record:

1. image/container/resource limits;
2. workload profile and duration;
3. concurrency step/ramp;
4. p50/p95/p99 + error rate;
5. CPU/RSS/event-loop or worker saturation;
6. DB pool/query/lock state;
7. queue depth/oldest age;
8. first observed saturation point;
9. accepted safe operating point with headroom;
10. scale-out response and post-scale recovery.

## Cost model

Do not mix provider spend into platform unit cost.

```text
platform fixed/elastic cost
= API + Agent + Tool + Media + DB + Redis + RabbitMQ + object/CDN + observability

provider variable cost
= model/provider usage measured by Cost Ledger
```

NODE-72 freezes provider/region/instance prices. NODE-69 supplies measured safe concurrency and utilization so cost-per-capacity can be calculated without invented assumptions.

## Release gate

This plan is structurally complete, but every `PENDING` safe-concurrency value is a release blocker until production-like Profile G and component-specific profiles have actually run. A CI-local mock smoke is only harness validation, not launch capacity evidence. Dynamic target tracking must remain disabled until the corresponding measured signal and production emitter are both proven.
