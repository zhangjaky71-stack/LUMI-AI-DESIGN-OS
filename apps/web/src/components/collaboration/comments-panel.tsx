"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "@/lib/api/problem";
import {
  addThreadComment,
  createCommentThread,
  listCommentThreads,
  setCommentThreadStatus,
} from "@/lib/collaboration/api";
import type { CommentThreadBundle } from "@/lib/collaboration/types";
import type { ExactArtifactRef } from "@/lib/workspace/types";

export function CommentsPanel({
  organizationId,
  projectId,
  artifact,
  selectedNodeIds,
}: {
  organizationId: string;
  projectId: string;
  artifact: ExactArtifactRef;
  selectedNodeIds: readonly string[];
}) {
  const [threads, setThreads] = useState<readonly CommentThreadBundle[]>([]);
  const [loading, setLoading] = useState(true);
  const [newBody, setNewBody] = useState("");
  const [replyByThread, setReplyByThread] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const epoch = useRef(0);

  const refresh = useCallback(async (background = false) => {
    const currentEpoch = epoch.current;
    try {
      const next = await listCommentThreads(
        organizationId,
        projectId,
        artifact.artifactId,
        artifact.artifactVersionId,
        { includeHistory: true, includeResolved: true },
      );
      if (currentEpoch !== epoch.current) return;
      setThreads(next);
      if (!background) setNotice(null);
    } catch (error) {
      if (currentEpoch === epoch.current && !background) setNotice(message(error, "Comments are unavailable."));
    } finally {
      if (currentEpoch === epoch.current && !background) setLoading(false);
    }
  }, [organizationId, projectId, artifact.artifactId, artifact.artifactVersionId]);

  useEffect(() => {
    epoch.current += 1;
    setThreads([]);
    setLoading(true);
    setNotice(null);
    setNewBody("");
    setReplyByThread({});
    void refresh(false);
    const timer = window.setInterval(() => void refresh(true), 5_000);
    return () => {
      epoch.current += 1;
      window.clearInterval(timer);
    };
  }, [refresh]);

  const currentThreads = useMemo(
    () => threads.filter((item) => item.thread.artifactVersionId === artifact.artifactVersionId),
    [threads, artifact.artifactVersionId],
  );
  const historicalThreads = useMemo(
    () => threads.filter((item) => item.thread.artifactVersionId !== artifact.artifactVersionId),
    [threads, artifact.artifactVersionId],
  );
  const selectedNodeId = selectedNodeIds[0] ?? null;

  async function createThread() {
    const body = newBody.trim();
    if (!body || pending) return;
    setPending("create");
    setNotice(null);
    try {
      await createCommentThread(
        organizationId,
        projectId,
        artifact.artifactId,
        {
          artifactVersionId: artifact.artifactVersionId,
          designNodeId: selectedNodeId,
          body,
        },
      );
      setNewBody("");
      await refresh(false);
    } catch (error) {
      setNotice(message(error, "Could not create comment thread."));
    } finally {
      setPending(null);
    }
  }

  async function reply(threadId: string) {
    const body = (replyByThread[threadId] ?? "").trim();
    if (!body || pending) return;
    setPending(`reply:${threadId}`);
    setNotice(null);
    try {
      await addThreadComment(organizationId, threadId, body);
      setReplyByThread((current) => ({ ...current, [threadId]: "" }));
      await refresh(false);
    } catch (error) {
      setNotice(message(error, "Could not add reply."));
    } finally {
      setPending(null);
    }
  }

  async function toggleStatus(bundle: CommentThreadBundle) {
    if (pending) return;
    const next = bundle.thread.status === "OPEN" ? "RESOLVED" : "OPEN";
    setPending(`status:${bundle.thread.id}`);
    setNotice(null);
    try {
      await setCommentThreadStatus(organizationId, bundle.thread.id, next);
      await refresh(false);
    } catch (error) {
      setNotice(message(error, "Could not change thread status."));
    } finally {
      setPending(null);
    }
  }

  return (
    <section className="comments-panel" aria-labelledby="comments-title">
      <div className="comments-heading">
        <div><p className="eyebrow">Collaboration</p><h2 id="comments-title">Comments</h2></div>
        <button type="button" onClick={() => void refresh(false)}>Refresh</button>
      </div>
      <p className="comments-copy">Threads are bound to exact ArtifactVersion IDs. Historical threads are never auto-moved to this version.</p>

      <div className="comments-new-thread">
        <textarea
          value={newBody}
          onChange={(event) => setNewBody(event.target.value)}
          rows={3}
          maxLength={20_000}
          placeholder={selectedNodeId ? "Comment on the selected node…" : "Comment on this exact version…"}
        />
        <div>
          <span>{selectedNodeId ? `Node ${shortId(selectedNodeId)}` : `Version ${shortId(artifact.artifactVersionId)}`}</span>
          <button type="button" disabled={!newBody.trim() || pending !== null} onClick={() => void createThread()}>{pending === "create" ? "Posting…" : "Post"}</button>
        </div>
      </div>

      {notice ? <div className="comments-notice" role="status">{notice}</div> : null}
      {loading ? <p className="comments-muted">Loading durable threads…</p> : null}
      {!loading && currentThreads.length === 0 ? <p className="comments-muted">No comments on this exact version.</p> : null}

      <div className="comments-thread-list">
        {currentThreads.map((bundle) => (
          <ThreadCard
            key={bundle.thread.id}
            bundle={bundle}
            reply={replyByThread[bundle.thread.id] ?? ""}
            onReplyChange={(value) => setReplyByThread((current) => ({ ...current, [bundle.thread.id]: value }))}
            onReply={() => void reply(bundle.thread.id)}
            onToggleStatus={() => void toggleStatus(bundle)}
            pending={pending}
            historical={false}
          />
        ))}
      </div>

      {historicalThreads.length ? (
        <details className="comments-history">
          <summary>{historicalThreads.length} historical thread{historicalThreads.length === 1 ? "" : "s"} · needs review before re-anchor</summary>
          <div className="comments-thread-list">
            {historicalThreads.map((bundle) => (
              <ThreadCard
                key={bundle.thread.id}
                bundle={bundle}
                reply=""
                onReplyChange={() => undefined}
                onReply={() => undefined}
                onToggleStatus={() => undefined}
                pending={pending}
                historical
              />
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
}

function ThreadCard({
  bundle,
  reply,
  onReplyChange,
  onReply,
  onToggleStatus,
  pending,
  historical,
}: {
  bundle: CommentThreadBundle;
  reply: string;
  onReplyChange: (value: string) => void;
  onReply: () => void;
  onToggleStatus: () => void;
  pending: string | null;
  historical: boolean;
}) {
  const thread = bundle.thread;
  return (
    <article className={`comments-thread${historical ? " is-historical" : ""}`}>
      <div className="comments-thread-top">
        <div>
          <strong>{thread.status}</strong>
          {thread.designNodeId ? <span>Node {shortId(thread.designNodeId)}</span> : <span>Version-level</span>}
          {historical || thread.needsReanchor ? <span className="comments-reanchor">NEEDS RE-ANCHOR</span> : null}
        </div>
        {!historical ? <button type="button" disabled={pending !== null} onClick={onToggleStatus}>{thread.status === "OPEN" ? "Resolve" : "Reopen"}</button> : null}
      </div>
      <p className="comments-version-id">Exact version {shortId(thread.artifactVersionId)}</p>
      <div className="comments-messages">
        {bundle.comments.map((comment) => (
          <div key={comment.id} className={comment.deletedAt ? "is-deleted" : ""}>
            <p>{comment.body}</p>
            <small>{shortId(comment.createdBy)} · {formatTime(comment.createdAt)}{comment.editedAt ? " · edited" : ""} · r{comment.revision}</small>
          </div>
        ))}
      </div>
      {!historical && thread.status === "OPEN" ? (
        <div className="comments-reply">
          <input value={reply} onChange={(event) => onReplyChange(event.target.value)} maxLength={20_000} placeholder="Reply…" />
          <button type="button" disabled={!reply.trim() || pending !== null} onClick={onReply}>{pending === `reply:${thread.id}` ? "Sending…" : "Reply"}</button>
        </div>
      ) : null}
    </article>
  );
}

function shortId(value: string): string { return value.length > 14 ? `${value.slice(0, 7)}…${value.slice(-4)}` : value; }
function formatTime(value: string): string { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date); }
function message(error: unknown, fallback: string): string { if (error instanceof ApiError) return error.detail || error.title || fallback; return error instanceof Error ? error.message : fallback; }
