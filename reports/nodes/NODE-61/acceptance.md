# NODE-61 Acceptance Evidence — Collaboration Engine

Status: **CORE_IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implemented and reviewable

- Durable PostgreSQL `comment_threads`, `comments`, and `comment_revisions` with linear Alembic migration `20260818_0020 -> 20260818_0021`.
- Comment threads bind exact `artifact_version_id`, optional `design_node_id`, and optional coordinate anchor.
- Historical threads are returned with `needs_reanchor`; the API and Workspace never silently rewrite them to the currently open version.
- Comment create/reply, revision-fenced edit/delete, resolve/reopen, restricted revision audit, and validated mentions.
- Mention Outbox payload contains IDs only; it does not copy comment body into the notification event.
- Project access is fail-closed through organization membership plus Project creator or explicit `project_members` membership.
- Presence is ephemeral only: 10s heartbeat contract, 30s TTL, no SQLAlchemy/Alembic presence table.
- Presence `user_id` and display identity are server authoritative. Heartbeat cannot submit user ID, display name, or avatar URL.
- Collaboration routes contain no DesignDocument/Canvas mutation endpoint; design edits remain behind NODE-55 DesignOps and its version/constraint fences.
- Workspace Inspector mounts `CommentsPanel` for the selected exact ArtifactVersion and passes the current Canvas node selection only as an optional new-thread anchor.

## Explicitly not accepted as complete

- Production Redis PresencePort/composition.
- Authenticated WebSocket/SSE collaboration gateway, fanout ordering, reconnect/rebase, and disconnect cleanup.
- Role-aware hiding/disabling of collaboration controls before server rejection.
- Mention picker and proven notification delivery consumer/UI.
- Comment edit/delete/audit browser controls.
- Explicit reviewed re-anchor workflow.
- Realtime multi-user Canvas conflict UX / operation fanout.
- Large-thread cursor pagination and retention/privacy administration.
- Browser + PostgreSQL + Redis multi-user E2E.
- Hosted GitHub Actions executing the NODE-61 commands green.

## Acceptance rule

NODE-61 remains **NOT COMPLETE** while any P0 gap in `gap-ledger.json` is open or Hosted CI has not executed real steps successfully.
