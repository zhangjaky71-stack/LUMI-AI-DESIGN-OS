# Collaboration Engine Runtime Contract V1

Status: NODE-61 core implementation contract.

## Canonical truth boundaries

Collaboration adds people, comments, presence and coordination around existing LUMI resources. It does **not** become a second source of truth for DesignDocument or Artifact history.

- Design edits continue through NODE-55 Canvas Design Operations and existing document/version/constraint fences.
- Artifact approval remains NODE-42 ArtifactVersion state.
- Comment resolution is not approval.
- Fork/restore/version history remain NODE-59/NODE-42 operations.
- Presence is ephemeral and must never be treated as durable project state.

## Durable comment model

Three PostgreSQL resources are added in migration `20260818_0021`:

1. `comment_threads`
   - tenant/project/artifact identity;
   - exact `artifact_version_id`;
   - optional `design_node_id` or x/y anchor;
   - OPEN/RESOLVED status;
   - explicit `needs_reanchor` marker;
   - creator/resolver audit fields.
2. `comments`
   - thread identity;
   - body and mention-user IDs;
   - creator;
   - revision integer;
   - edited/deleted timestamps.
3. `comment_revisions`
   - immutable CREATED/EDITED/DELETED snapshots;
   - body and mention snapshot;
   - actor and revision number.

Deleting a Comment does not erase its audit snapshot. Product reads replace the current body with `[deleted]`; revision history remains restricted to the Comment owner or Project admin.

## Exact-version binding and re-anchor

A new Thread is accepted only when the exact ArtifactVersion belongs to the same tenant, Project and Artifact supplied by the route.

When listing historical Artifact threads against a newer current version, the service derives `needs_reanchor=true` when the stored exact version differs. It does not rewrite the Thread's original `artifact_version_id` and does not automatically choose a new node/coordinate.

## Access control

Collaboration requires a real user UUID actor. Project access is fail-closed:

- Project creator is treated as Project admin;
- otherwise the user must have an explicit `project_members` row;
- Project admin/editor/viewer may read and create comments;
- Comment edits/deletes require Comment owner or Project admin;
- Thread resolve/reopen requires Thread creator or Project editor/admin;
- Comment audit history requires Comment owner or Project admin.

Organization membership alone is not enough to access a Project's collaboration data.

## Optimistic concurrency

Comment PATCH and DELETE require `If-Match` with the current positive Comment revision. A stale revision raises conflict instead of silently replacing another collaborator's edit.

Thread resolution is state coordination only and never changes ArtifactVersion status.

## Mentions

Mention IDs must identify real organization users who can access the same Project. Mention creation is written to the existing Outbox in the same database transaction as the Comment/Revision mutation.

The notification payload contains IDs only:

- Project ID;
- Thread ID;
- Comment ID;
- mentioned user ID;
- actor ID.

The Comment body is intentionally not copied into the Outbox payload.

## Presence

Presence has **no PostgreSQL model or migration table**.

Contract values:

- TTL: 30 seconds;
- recommended heartbeat: 10 seconds;
- user actor identity;
- project/exact ArtifactVersion/frame context;
- optional cursor and node selection;
- last-seen timestamp.

`InMemoryPresencePort` is for deterministic tests/dev only. Production requires a Redis-backed PresencePort and authenticated realtime transport before NODE-61 can be COMPLETE.

## Realtime editing

NODE-61 exposes no API that mutates DesignDocument nodes. Collaboration transport must submit edits through the existing Canvas Design Operations endpoint. This keeps:

- server document-version fencing;
- structural operation validation;
- constraint validation;
- Brand enforcement;
- Artifact/version provenance.

A future WebSocket may distribute presence and canonical operation acknowledgements, but it must not become a freeform CRDT bypass around server DesignOps.

## Privacy

Collaboration routes must not carry raw provider/tool payloads, system prompts, hidden reasoning or secrets. Presence is best-effort and short-lived. Comments are durable project content and follow tenant/project access rules.

## Current product surface

The branch contains a strict web Comment client and `CommentsPanel` supporting:

- current exact-version threads;
- historical thread display with NEEDS RE-ANCHOR;
- optional selected-node binding;
- create/reply;
- resolve/reopen;
- polling refresh.

Workspace mounting, collaborator profile/mention picker, production Redis/WebSocket transport and full browser E2E remain open P0 items.
