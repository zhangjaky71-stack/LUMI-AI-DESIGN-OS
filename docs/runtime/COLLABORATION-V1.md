# Collaboration Runtime V1

## Runtime topology

```text
Web / Collaboration UI
  ├─ GET Project collaboration bootstrap
  ├─ POST review-thread commands
  ├─ POST canonical Design Operations
  ├─ POST reconnect/rebase
  └─ WebSocket awareness only
       ↓
Collaboration Router
  ├─ trusted NODE-16 actor resolver
  ├─ trusted Project workspace metadata resolver
  ├─ CollaborationEngine
  │    ├─ AuthorizationPort
  │    ├─ CollaborationRepository
  │    ├─ CanonicalDesignPort (NODE-40)
  │    ├─ ConstraintValidationPort
  │    ├─ AuditPort
  │    └─ NotificationPort
  └─ RealtimeHubPort
```

## Canonical truth

Presence, cursor and selection awareness are disposable. Review threads, operation audit and exact version anchors are durable. Design mutations are canonical only after the Design Operation path creates/advances a DesignDocumentVersion.

Do not restore design truth from a WebSocket/CRDT snapshot after a realtime restart. Restore realtime state from the canonical document and let users republish awareness.

## Production bindings required

`create_collaboration_router()` deliberately requires trusted actor and workspace metadata resolvers. The module does not parse access tokens itself. Production wiring must bind these resolvers to NODE-16 Auth/Tenant session state and the canonical Project member directory.

`CanonicalDesignPort` must bind to NODE-40's server-authorized Design Operation / DesignDocumentVersion implementation. The in-memory canonical adapter exists only for deterministic tests.

`CollaborationRepository`, audit and notifications must bind to PostgreSQL tables from `0011_collaboration.sql`. The sequence intentionally follows existing `0009_visual_critic.sql` and `0010_auto_repair.sql`. Presence and realtime fanout must use an ephemeral multi-instance adapter (for example Redis) rather than SQL.

## WebSocket rules

Allowed:

- `AWARENESS_UPDATE`;
- presence snapshots/fanout.

Rejected:

- `DESIGN_OPERATION`;
- `CRDT_UPDATE` as a canonical write;
- `CANONICAL_WRITE`.

No bearer/session token is accepted from WebSocket query parameters by the collaboration router.

## Reconnect procedure

1. keep local safe operations in an ephemeral client buffer;
2. reconnect using the exact base DesignDocumentVersion;
3. server loads canonical head and committed operations since base;
4. rebase operations with distinct `(node_id, property_name)` keys;
5. keep same-property local operations in the conflict response;
6. user resolves explicit conflicts;
7. Hard Constraints validate every accepted commit.

## Operational signals

Track without sensitive payloads:

- active collaboration rooms;
- presence connection count;
- thread create/reply/resolve rates;
- operation rebase rate;
- operation conflict rate;
- reconnect rate;
- Hard Constraint rejection count;
- realtime reconnect/error count;
- AGENT action count by `agent_run_id` reference.

Do not log full comment bodies, raw asset payloads, auth tokens or CRDT binary updates in operational logs.

## Failure posture

- auth/member resolver unavailable → fail closed;
- canonical Design Operation service unavailable → keep local edit buffered and do not acknowledge commit;
- realtime unavailable → comments/canonical REST paths may continue; presence shows Offline;
- DB unavailable → durable comments fail rather than fall back to browser persistence;
- Hard Constraint failure → reject canonical commit;
- stale same-property edit → explicit conflict, no silent LWW.
