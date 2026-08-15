# NODE-57 Acceptance Evidence

> Node: Agent Timeline & Run Observability UX  
> Status: IMPLEMENTED / VALIDATING / NOT COMPLETE  
> Base: `node-56-layers-inspector-release` @ `e04125f7cb45bc6554a05abcceb9d2de1c47ac94`

## Implemented product surface

- Agent panel upgraded from a flat status/card feed to a canonical Agent Timeline.
- Run and Task state projection from `AIWorkspaceSnapshot`.
- Filters: All / Agent / Generation / Approval / Error.
- Real child-count progress (`completed_units / total_units`), never invented reasoning percentages.
- Safe tool-action summaries.
- Safe error code/message/request id/retrying/provider fallback display.
- Retry action delegates to existing versioned Agent Run gateway.
- Current pending Approval becomes sticky `WAITING_USER`.
- Stale Approval remains visible and non-actionable.
- Artifact cards retain exact ArtifactVersion and existing placement/reference actions.
- Canvas handoff action added without claiming exact-node convergence that the backend does not yet provide.
- Optional Run/Task/Approval cost summaries are collapsible.
- Explicit cancelled terminal state.
- Mobile Timeline remains inside the focused Agent panel.

## Canonical recovery truth

Timeline does not persist its own event log. It is recomputed from the current workspace snapshot. Existing SSE behavior remains:

```text
Last-Event-ID reconnect
+ event-id dedupe
+ applyWorkspaceEvent()
+ canonical refetch after stream
```

A deterministic seeded failed Run verifies that refresh can rebuild the same Timeline without browser event history.

## Safety truth

The observability type extension intentionally contains only safe fields. Unknown runtime/debug fields are not copied by the projector.

`sanitizeTimelineText()` additionally hides strings resembling:

- system prompts;
- private chain-of-thought;
- raw tool payload/results/args;
- bearer authorization;
- API keys;
- stack traces;
- private markers.

This is defense in depth and does not replace backend safe-summary policy.

## Deterministic fixtures

Non-production E2E only:

- `project-agent-retry`: failed retryable generation Task, 2/4 progress, safe request id and provider fallback.
- `project-agent-cancelled`: terminal canceled Run and canceled remaining generation Task.

The production build gate scans static client chunks for the retry fixture identifier.

## Unit coverage staged

- canonical Run/Task projection;
- actual progress counts;
- safe tool summaries;
- unknown debug field exclusion;
- suspicious private-text redaction;
- safe error/fallback/request id;
- sticky current approval vs stale approval;
- deterministic refresh reconstruction.

## Browser coverage staged

- streamed safe stages;
- duplicate SSE delivery remains deduplicated;
- waiting-user Approval is pinned;
- provider fallback filter;
- failed Task retry;
- refresh recovery from canonical seeded state;
- canceled Run terminal state;
- exact ArtifactVersion Canvas handoff;
- approval action regression;
- no raw execution payload leakage.

NODE-54 AI Workspace, NODE-55 Infinite Canvas and NODE-56 Layers/Inspector browser suites remain regression dependencies.

## Static gate

```text
python scripts/validate_agent_timeline.py
```

The validator checks canonical projection ownership, safe model shape, frontend redaction, actual progress counts, sticky approval, ArtifactVersion retention, retry wiring, fallback/cancel fixtures, refresh/duplicate tests, and absence of durable browser Timeline truth.

## Hosted workflow

`.github/workflows/agent-timeline.yml` defines:

```text
agent-timeline-contract
agent-timeline-quality
agent-timeline-build
agent-timeline-browser-e2e
```

Pinned environment follows the repository product chain: Ubuntu 24.04, Node 24, pnpm 11.4.0 and Python 3.12 where required.

## Hosted evidence

Not recorded yet. The workflow must be observed after the Draft PR is created.

Previous NODE-53 through NODE-56 workflows were blocked before runner start by GitHub account payment/spending-limit state. NODE-57 must be judged independently from its actual run evidence; the same platform annotation, if observed, is not a PASS and is not a code/test failure.

## Production dependency truth

NODE-57 does not claim:

- all production Agent Tasks already populate every new optional observability field;
- AI Workspace Artifact placement and NODE-55 Canvas operations persistence are fully converged;
- exact Artifact → Canvas node navigation exists before that convergence;
- hosted validation has passed before runners execute.

## Current verdict

```text
canonical Timeline projection       IMPLEMENTED
safe summary/redaction boundary     IMPLEMENTED
Run/Task status UX                  IMPLEMENTED
actual child-count progress         IMPLEMENTED
safe tool visibility                IMPLEMENTED
error/retry/fallback UX             IMPLEMENTED
sticky Approval                     IMPLEMENTED
ArtifactVersion actions             IMPLEMENTED
cost summary                        IMPLEMENTED
filters                             IMPLEMENTED
unit/browser coverage               STAGED
static architecture gate            STAGED
hosted pinned gates                 PENDING EXECUTION
production observability coverage   BACKEND INTEGRATION DEPENDENCY
exact Canvas artifact-node jump     INTEGRATION DEPENDENCY
```

NODE-57 is **IMPLEMENTED / VALIDATING / NOT COMPLETE**.
