# NODE-61 — Collaboration

> Phase: 8 SaaS & Collaboration  
> Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Priority: P0  
> Depends on: NODE-16 Auth/Tenant, NODE-40 Canvas Engine, NODE-42 Artifact Engine, NODE-52 App Shell  
> Produces: tenant-scoped review threads, mentions, ephemeral presence, concurrent Design Operation rebase/conflict semantics, AI actor audit and Collaboration product UX

---

## 1. Goal

NODE-61 lets Designers, Marketing, Managers, Clients and AI Agents work against one Project without turning WebSocket/CRDT runtime state into a second source of truth.

Canonical invariant:

```text
NODE-16 authorized actor
  -> Project collaboration context
  -> ephemeral realtime awareness (presence/cursor/selection)
  -> durable review threads bound to exact versions
  -> server-authorized Design Operations
  -> reconnect/rebase/conflict
  -> Hard Constraint validation
  -> canonical DesignDocumentVersion / Artifact history
```

`CRDT state != canonical Design IR history`.

## 2. Product route

```text
/app/projects/{projectId}/collaboration
```

The Project surface now links to Collaboration alongside Workspace, Versions and Export.

The product UI exposes:

- Team & Presence;
- USER vs AGENT identity;
- exact-version review threads;
- mentions and safe in-app notifications;
- OPEN / RESOLVED / REOPENED lifecycle;
- historical-node review context;
- concurrent-edit safety explanation;
- explicit reconnect conflict UI;
- responsive mobile layout.

## 3. Presence is ephemeral

`PresenceState` contains only realtime awareness:

```text
organization_id
project_id
document_id
actor
cursor?
selection_ids[]
active_frame_id?
last_seen
```

Presence is never written to the collaboration SQL migration or Design IR. The in-process hub/store is a deterministic development/test adapter only. Multi-instance production must bind the same protocol to Redis or another authorized realtime fanout service.

A realtime restart may clear cursor/selection state, but must not erase comments or canonical Design Operations.

## 4. Durable review threads

Every `CommentAnchor` is immutable and exact:

```text
project_id
artifact_version_id
design_document_version_id
node_id?
frame_id?
canvas region?
```

Floating identifiers `latest`, `head`, and `current` are rejected.

A thread attached to a node deleted in a later version remains viewable because its exact historical ArtifactVersion/DesignVersion anchor is retained.

Thread states:

```text
OPEN
RESOLVED
REOPENED
```

Edit/delete is represented as durable audit semantics; deletion tombstones the message instead of erasing the review event.

## 5. Mentions and permissions

Authorization is a port owned by NODE-16 integration. Collaboration does **not** invent a second RBAC model. Effective roles are the canonical NODE-16 roles:

```text
OWNER
ADMIN
EDITOR
VIEWER
BILLING
```

Product policy:

- OWNER / ADMIN / EDITOR → view, review and canonical design edit;
- VIEWER → view and review/comment when Project review policy permits;
- BILLING → no collaboration comment/edit capability;
- a client reviewer is a product persona represented by an authorized VIEWER, not a new `CLIENT` Auth role;
- mention target must also be authorized for the same organization/project.

The collaboration router never accepts an auth token in request payloads or WebSocket query parameters. It requires trusted HTTP/WS actor resolvers supplied by the NODE-16 session/tenant runtime.

## 6. AI Agent actor

AI participation is first-class and auditable:

```text
actor_type = AGENT
actor_id
agent_run_id (required)
effective role = delegated canonical NODE-16 role
```

Actor type and effective role are orthogonal: `AGENT` identifies who performed the action; the delegated NODE-16 role controls what that actor may do. A USER may not carry an `agent_run_id`, and an AGENT may not omit it.

Agent comments/operations pass through the same authorization port as human actions. An Agent cannot gain permissions simply by entering the collaboration room.

## 7. Canonical concurrent editing

Browser-local optimistic changes are not committed directly through WebSocket.

Canonical path:

```text
POST /projects/{projectId}/documents/{documentId}/collaboration/operations
```

Conflict key for P0:

```text
(node_id, property_name)
```

Rules:

1. base == canonical head → validate → commit;
2. stale base + no matching conflict key → rebase safe operations → validate → commit;
3. stale base + same conflict key → return explicit conflict;
4. local conflicting operation is returned intact to the caller;
5. no silent last-write-wins loss;
6. Hard Constraint validator always runs before accepted canonical operations commit.

The canonical port is intentionally a boundary to NODE-40 Design Operation / DesignDocumentVersion infrastructure rather than a second scene graph.

## 8. Reconnect

Reconnect uses the same operation semantics:

```text
buffer safe local ops
  -> reconnect
  -> fetch canonical head
  -> inspect operations since base
  -> rebase non-conflicting operations
  -> surface same-property conflicts
  -> preserve local buffered value
```

The collaboration engine never silently drops a buffered edit.

## 9. Realtime transport boundary

WebSocket route:

```text
/projects/{projectId}/collaboration/ws?document_id=...
```

Allowed realtime payload:

```text
AWARENESS_UPDATE
PRESENCE_SNAPSHOT
```

Explicitly rejected over WebSocket:

```text
DESIGN_OPERATION
CRDT_UPDATE
CANONICAL_WRITE
```

All business writes remain server-authorized HTTP commands that normalize to canonical Design Operations.

## 10. API bootstrap

Project entry does not let the browser guess a `document_id`.

```text
GET /projects/{projectId}/collaboration
```

A trusted server `WorkspaceMetadataResolver` resolves:

- exact collaboration document ID;
- exact ArtifactVersion;
- current authorized user projection;
- same-project member directory;
- safe notification summaries.

The collaboration engine then resolves the canonical DesignDocumentVersion for that exact document.

## 11. Persistence

Migration:

```text
db/migrations/0011_collaboration.sql
```

`0011` is intentionally after the existing `0009_visual_critic.sql` and `0010_auto_repair.sql`; NODE-61 does not introduce a duplicate migration number.

Durable tables:

```text
collaboration_threads
collaboration_comments
collaboration_operation_commits
collaboration_audit_events
collaboration_notifications
```

There is intentionally **no collaboration presence table**.

Thread references from comments and notifications use organization + project + thread composite foreign keys, preventing a durable cross-tenant/cross-project thread reference even if a thread UUID were known.

Persistent records retain USER/AGENT actor identity and `agent_run_id` invariants.

## 12. Security boundaries

- tenant/project authorization before presence room join;
- same-project mention validation;
- tenant/project composite thread references in SQL;
- no tokens in realtime query payload;
- no WebSocket canonical mutation;
- no browser localStorage/sessionStorage/IndexedDB canonical collaboration truth;
- no CRDT type leakage into Artifact/Agent/Export contracts;
- comment body length bounded;
- realtime selection count bounded;
- safe notifications exclude asset payloads/secrets;
- exact historical anchors are immutable.

## 13. Tests staged

Backend engine:

- two users, stale base, different-node merge;
- same-property explicit conflict;
- local edit preservation on reconnect;
- tenant-isolated presence;
- historical deleted-node comment;
- mention permission;
- Hard Constraint fail-closed;
- AGENT run identity;
- realtime restart recovery from canonical truth.

API transport:

- trusted Project bootstrap;
- exact thread anchor;
- HTTP canonical operations;
- reconnect conflict;
- WebSocket awareness;
- WebSocket canonical-write rejection.

Browser:

- presence/team;
- AI actor;
- exact-version mention/comment;
- historical thread;
- resolve/reopen;
- canonical version advance;
- reconnect conflict/local preservation;
- canonical truth boundary;
- mobile.

## 14. Known production integration gates

The protocol, engine, migration, API router factory and product UI are implemented. NODE-61 remains NOT COMPLETE until these deployment adapters are connected and validated in the target environment:

1. NODE-16 trusted session/tenant resolver + Project member directory bound to `create_collaboration_router`;
2. durable PostgreSQL repository/audit/notification adapter bound to the migration tables;
3. NODE-40 canonical Design Operation / DesignDocumentVersion adapter bound to `CanonicalDesignPort`;
4. Redis/managed realtime hub replacing the in-process fanout for multi-instance deployment;
5. hosted pinned CI actually executes green.

These are explicit integration gates, not simulated as production readiness.

## 15. Acceptance

- [x] team presence/review product UI implemented;
- [x] exact ArtifactVersion/DesignVersion comment anchors;
- [x] mentions and thread lifecycle;
- [x] canonical NODE-16 role vocabulary preserved;
- [x] realtime state cannot become canonical design history;
- [x] WebSocket canonical writes rejected;
- [x] non-conflicting stale operations rebase;
- [x] same-property conflicts preserve local edit;
- [x] Hard Constraint validation is in canonical commit path;
- [x] Agent actor/run audit identity;
- [x] durable schema excludes presence and scopes thread references by tenant/project;
- [x] backend/frontend/static/browser tests staged;
- [ ] NODE-16/DB/NODE-40 production adapters connected;
- [ ] multi-instance realtime adapter connected;
- [ ] hosted pinned gates observed green.

## 16. Definition of Done

```text
collaboration contract green
+ backend concurrency/reconnect tests green
+ PostgreSQL migration green
+ multi-user browser E2E green
+ NODE-16 / NODE-40 / durable repository adapters connected
+ multi-instance realtime validated
```

Next: **NODE-62 — Approval Engine**.
