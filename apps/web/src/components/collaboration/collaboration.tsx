"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { anchorLabel, canComment, canEdit, mentionOptions, safeCollaborationError, shortAgentRun } from "@/lib/collaboration/contracts";
import { createCollaborationGateway } from "@/lib/collaboration/collaboration-gateway";
import type {
  CollaborationBootstrap,
  CollaborationConflict,
  CollaborationRealtimeEvent,
  CollaborationThread,
  CollaborationWorkspaceSnapshot,
} from "@/lib/collaboration/types";
import styles from "./collaboration.module.css";

export function Collaboration({ projectId, bootstrap }: Readonly<{ projectId: string; bootstrap: CollaborationBootstrap }>) {
  const gateway = useMemo(() => createCollaborationGateway(bootstrap), [bootstrap]);
  const [workspace, setWorkspace] = useState<CollaborationWorkspaceSnapshot | null>(bootstrap.workspace ?? null);
  const [connection, setConnection] = useState<"Connected" | "Reconnecting" | "Offline">("Offline");
  const [filter, setFilter] = useState<"ALL" | "OPEN" | "RESOLVED">("ALL");
  const [comment, setComment] = useState("");
  const [mention, setMention] = useState("");
  const [replyByThread, setReplyByThread] = useState<Record<string, string>>({});
  const [conflict, setConflict] = useState<CollaborationConflict | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let realtime: { close(): void } | null = null;
    void gateway.loadWorkspace(projectId, controller.signal).then((snapshot) => {
      if (controller.signal.aborted) return;
      setWorkspace(snapshot);
      realtime = gateway.openRealtime(projectId, snapshot.document_id, (event) => {
        handleRealtimeEvent(event, setConnection, setWorkspace);
      });
    }).catch((error) => {
      if (controller.signal.aborted) return;
      const safe = safeCollaborationError(error);
      setNotice(safe.message);
      setRequestId(safe.request_id);
    });
    return () => {
      controller.abort();
      realtime?.close();
    };
  }, [gateway, projectId]);

  if (!workspace) {
    return <main className={styles.shell}><p>Loading collaboration workspace…</p>{notice ? <p>{notice}</p> : null}</main>;
  }

  const editable = canEdit(workspace.current_user.role);
  const commentable = canComment(workspace.current_user.role);
  const mentions = mentionOptions(workspace.current_user, workspace.members);
  const visibleThreads = workspace.threads.filter((thread) => {
    if (filter === "ALL") return true;
    if (filter === "OPEN") return thread.status === "OPEN" || thread.status === "REOPENED";
    return thread.status === "RESOLVED";
  });

  const refresh = async () => setWorkspace(await gateway.loadWorkspace(projectId));

  const postThread = async () => {
    if (!commentable || !comment.trim()) return;
    try {
      await gateway.createThread(projectId, {
        body: comment,
        mention_actor_ids: mention ? [mention] : [],
        anchor: {
          artifact_version_id: workspace.artifact_version_id,
          design_document_version_id: workspace.canonical_version_id,
          node_id: "hero-title",
          frame_id: "frame-instagram",
        },
      });
      setComment("");
      setMention("");
      await refresh();
      setNotice("Comment posted on the exact current version.");
    } catch (error) {
      showError(error, setNotice, setRequestId);
    }
  };

  const reply = async (thread: CollaborationThread) => {
    const body = replyByThread[thread.thread_id]?.trim();
    if (!body) return;
    try {
      await gateway.reply(projectId, thread.thread_id, { body, mention_actor_ids: [] });
      setReplyByThread((current) => ({ ...current, [thread.thread_id]: "" }));
      await refresh();
    } catch (error) {
      showError(error, setNotice, setRequestId);
    }
  };

  const changeStatus = async (thread: CollaborationThread) => {
    const status = thread.status === "RESOLVED" ? "REOPENED" : "RESOLVED";
    try {
      await gateway.setThreadStatus(projectId, thread.thread_id, status);
      await refresh();
    } catch (error) {
      showError(error, setNotice, setRequestId);
    }
  };

  const simulateSafeEdit = async () => {
    if (!editable) return;
    setConflict(null);
    const result = await gateway.submitOperations(projectId, workspace.document_id, {
      base_version_id: workspace.canonical_version_id,
      operations: [{
        operation_id: crypto.randomUUID(),
        node_id: "cta",
        property_name: "fill",
        value: "#181818",
      }],
    });
    setWorkspace((current) => current ? { ...current, canonical_version_id: result.canonical_version_after } : current);
    setNotice("Non-conflicting operation committed through the canonical Design Operation API.");
  };

  const simulateReconnectConflict = async () => {
    if (!editable) return;
    const base = workspace.canonical_version_id;
    const result = await gateway.reconnect(projectId, workspace.document_id, {
      base_version_id: base,
      operations: [{
        operation_id: crypto.randomUUID(),
        node_id: "hero-title",
        property_name: "text",
        value: "Local buffered headline",
      }],
    });
    setWorkspace((current) => current ? { ...current, canonical_version_id: result.canonical_version_after } : current);
    setConflict(result.conflicts[0] ?? null);
    setNotice(result.conflicts.length ? "Reconnect found a same-property conflict. The local edit remains buffered." : "Reconnect rebased safely.");
  };

  return (
    <main className={styles.shell}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>NODE-61 · MULTI-USER DESIGN OPERATIONS</p>
          <h1>Collaboration</h1>
          <p>Human review, AI participation, ephemeral presence, and server-authorized concurrent edits on one canonical design history.</p>
        </div>
        <div className={styles.headerMeta}>
          <span className={styles.connection} data-state={connection.toLowerCase()} data-testid="connection-status">{connection}</span>
          <span data-testid="canonical-version">Canonical <code>{workspace.canonical_version_id}</code></span>
          <Link href={`/app/projects/${encodeURIComponent(projectId)}/workspace`}>Open Canvas</Link>
        </div>
      </header>

      <section className={styles.truthBoundary} data-testid="truth-boundary">
        <strong>Canonical truth:</strong> Presence/cursor/selection are ephemeral WebSocket awareness. Design writes go through the HTTP Design Operation API and become a new DesignDocumentVersion after authorization, rebase and Hard Constraint validation. CRDT/realtime state is never the sole design history.
      </section>

      {notice ? <div className={styles.notice} data-testid="notice">{notice}{requestId ? <> · Request <code>{requestId}</code></> : null}</div> : null}

      <div className={styles.layout}>
        <aside className={styles.sideColumn}>
          <section className={styles.panel} data-testid="team-presence">
            <div className={styles.sectionHeading}><h2>Team & Presence</h2><span>{workspace.presence.length} online</span></div>
            <div className={styles.memberList}>
              {workspace.members.map((member) => {
                const live = workspace.presence.find((item) => item.actor.actor_id === member.actor_id);
                const run = shortAgentRun(member);
                return <div className={styles.member} key={member.actor_id}>
                  <div className={styles.avatar}>{member.actor_type === "AGENT" ? "AI" : member.display_name.slice(0, 1)}</div>
                  <div><strong>{member.display_name}</strong><small>{member.actor_type === "AGENT" ? "AI Agent" : member.role}{run ? ` · ${run}` : ""}</small>{live ? <small className={styles.live}>● {live.active_frame_id ?? "Project"} · {live.selection_ids.join(", ") || "Viewing"}</small> : <small>Offline</small>}</div>
                </div>;
              })}
            </div>
          </section>

          <section className={styles.panel} data-testid="notifications">
            <div className={styles.sectionHeading}><h2>Notifications</h2><span>{workspace.notifications.filter((item) => !item.read).length} new</span></div>
            {workspace.notifications.map((item) => <div className={styles.notification} key={item.notification_id}><strong>{item.kind.replace("_", " ")}</strong><p>{item.safe_summary}</p></div>)}
          </section>
        </aside>

        <section className={styles.panel}>
          <div className={styles.sectionHeading}><h2>Review Threads</h2><div className={styles.filterRow}>{(["ALL", "OPEN", "RESOLVED"] as const).map((item) => <button aria-pressed={filter === item} key={item} onClick={() => setFilter(item)}>{item}</button>)}</div></div>

          <div className={styles.composer}>
            <textarea data-testid="comment-composer" disabled={!commentable} value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Add review feedback to the current exact version…" />
            <div className={styles.composerActions}>
              <label>Mention <select data-testid="mention-select" value={mention} onChange={(event) => setMention(event.target.value)}><option value="">No mention</option>{mentions.map((member) => <option key={member.actor_id} value={member.actor_id}>@{member.display_name}</option>)}</select></label>
              <span>Anchors to <code>{workspace.artifact_version_id}</code> + <code>{workspace.canonical_version_id}</code></span>
              <button data-testid="post-comment" disabled={!commentable || !comment.trim()} onClick={() => void postThread()}>Post comment</button>
            </div>
          </div>

          <div className={styles.threads} data-testid="review-threads">
            {visibleThreads.map((thread) => <article className={styles.thread} key={thread.thread_id} data-status={thread.status}>
              <div className={styles.threadHeader}>
                <div><span className={styles.status}>{thread.status}</span><strong>{anchorLabel(thread, workspace.canonical_version_id)}</strong></div>
                <button onClick={() => void changeStatus(thread)}>{thread.status === "RESOLVED" ? "Reopen" : "Resolve"}</button>
              </div>
              <div className={styles.exactAnchor} data-testid={`anchor-${thread.thread_id}`}><code>{thread.anchor.artifact_version_id}</code><span>→</span><code>{thread.anchor.design_document_version_id}</code>{thread.anchor.historical ? <em>Historical snapshot retained</em> : null}</div>
              {thread.messages.map((message) => <div className={styles.message} key={message.comment_id}>
                <div className={styles.avatar}>{message.actor.actor_type === "AGENT" ? "AI" : message.actor.display_name.slice(0, 1)}</div>
                <div><p><strong>{message.actor.display_name}</strong>{message.actor.actor_type === "AGENT" ? <span className={styles.agentBadge}>AGENT · {shortAgentRun(message.actor)}</span> : null}</p><p>{message.deleted_at ? "Comment deleted · audit retained" : message.body}</p></div>
              </div>)}
              <div className={styles.replyRow}><input aria-label={`Reply to ${thread.thread_id}`} value={replyByThread[thread.thread_id] ?? ""} onChange={(event) => setReplyByThread((current) => ({ ...current, [thread.thread_id]: event.target.value }))} placeholder="Reply…" /><button onClick={() => void reply(thread)}>Reply</button></div>
            </article>)}
          </div>
        </section>

        <section className={`${styles.panel} ${styles.concurrentPanel}`} data-testid="concurrent-safety">
          <div className={styles.sectionHeading}><div><h2>Concurrent Edit Safety</h2><p>Optimistic locally, canonical on the server.</p></div></div>
          <div className={styles.safetyGrid}>
            <button data-testid="safe-edit" disabled={!editable} onClick={() => void simulateSafeEdit()}><strong>Different-node edit</strong><span>Commit a non-conflicting CTA fill operation.</span></button>
            <button data-testid="reconnect-conflict" disabled={!editable} onClick={() => void simulateReconnectConflict()}><strong>Reconnect same-property edit</strong><span>Show an explicit headline conflict; never silent LWW.</span></button>
          </div>
          {conflict ? <div className={styles.conflict} data-testid="conflict-banner"><strong>Conflict — local edit preserved</strong><p><code>{conflict.node_id}.{conflict.property_name}</code> was also changed by {conflict.remote_actor_id} in <code>{conflict.remote_result_version_id}</code>. Your buffered value remains available for manual resolution.</p></div> : null}
          <ul className={styles.rules}>
            <li>Different node/property ops can rebase.</li>
            <li>Same property edits surface a conflict instead of silently overwriting.</li>
            <li>Hard Constraints execute server-side before every accepted canonical commit.</li>
            <li>AI Agent actions keep <code>actor_type=AGENT</code> and exact <code>agent_run_id</code> audit identity.</li>
          </ul>
        </section>
      </div>
    </main>
  );
}

function handleRealtimeEvent(
  event: CollaborationRealtimeEvent,
  setConnection: (state: "Connected" | "Reconnecting" | "Offline") => void,
  setWorkspace: Dispatch<SetStateAction<CollaborationWorkspaceSnapshot | null>>,
): void {
  if (event.type === "CONNECTED") setConnection("Connected");
  if (event.type === "RECONNECTING") setConnection("Reconnecting");
  if (event.type === "OFFLINE") setConnection("Offline");
  if (event.type === "PRESENCE_SNAPSHOT") setWorkspace((current) => current ? { ...current, presence: event.presence } : current);
  if (event.type === "AWARENESS_UPDATE") setWorkspace((current) => {
    if (!current) return current;
    const rest = current.presence.filter((item) => item.actor.actor_id !== event.presence.actor.actor_id);
    return { ...current, presence: [...rest, event.presence] };
  });
}

function showError(error: unknown, setNotice: (value: string) => void, setRequestId: (value: string | null) => void): void {
  const safe = safeCollaborationError(error);
  setNotice(safe.message);
  setRequestId(safe.request_id);
}
