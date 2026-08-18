"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { decideApproval, listProjectApprovals, requestArtifactApproval } from "@/lib/approvals/api";
import type { ApprovalDecision, ApprovalResource } from "@/lib/approvals/types";
import { ApiError } from "@/lib/api/problem";
import type { ExactArtifactRef } from "@/lib/workspace/types";

export function ApprovalPanel({
  organizationId,
  projectId,
  currentArtifact,
  permissions,
  selectedNodeIds,
}: {
  organizationId: string;
  projectId: string;
  currentArtifact: ExactArtifactRef;
  permissions: readonly string[];
  selectedNodeIds: readonly string[];
}) {
  const [approvals, setApprovals] = useState<readonly ApprovalResource[]>([]);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<"request" | ApprovalDecision | null>(null);
  const [feedback, setFeedback] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const values = await listProjectApprovals(organizationId, projectId);
      setApprovals(values);
      setNotice(null);
    } catch (error) {
      setNotice(message(error, "Could not load approvals."));
    } finally {
      setLoading(false);
    }
  }, [organizationId, projectId]);

  useEffect(() => {
    let active = true;
    void refresh();
    const timer = window.setInterval(() => {
      if (active) void refresh();
    }, 15_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [refresh]);

  const exact = useMemo(
    () => approvals.filter((item) => item.artifactVersionId === currentArtifact.artifactVersionId),
    [approvals, currentArtifact.artifactVersionId],
  );
  const active = exact.find((item) => item.status === "PENDING") ?? null;
  const canRequest = permissions.includes("project.write");
  const canDecide = active ? permissions.includes(active.requiredPermission) : false;

  async function requestApproval() {
    if (!canRequest || pending) return;
    setPending("request");
    try {
      await requestArtifactApproval(organizationId, projectId, {
        artifactVersionId: currentArtifact.artifactVersionId,
        title: `Approve ${currentArtifact.label ?? "artifact"} ${currentArtifact.versionNumber ? `v${currentArtifact.versionNumber}` : "version"}`,
        summary: "Review this exact artifact version. Approval applies only to this immutable version and will not drift to a newer version.",
      });
      await refresh();
    } catch (error) {
      setNotice(message(error, "Could not request approval for this version."));
    } finally {
      setPending(null);
    }
  }

  async function decide(decision: ApprovalDecision) {
    if (!active || !canDecide || pending) return;
    const trimmed = feedback.trim();
    if (decision !== "APPROVED" && !trimmed) {
      setNotice("Reject and Request changes require feedback.");
      return;
    }
    setPending(decision);
    try {
      await decideApproval(organizationId, active.id, {
        decision,
        reason: decision === "APPROVED" ? null : trimmed,
        comment: trimmed || null,
        nodeIds: selectedNodeIds,
        requestedChanges: decision === "CHANGES_REQUESTED" && trimmed ? [trimmed] : [],
      });
      setFeedback("");
      await refresh();
    } catch (error) {
      setNotice(message(error, "Could not apply this approval decision."));
      await refresh();
    } finally {
      setPending(null);
    }
  }

  return (
    <section className="approval-panel" aria-label="Approval workflow">
      <div className="approval-heading">
        <div><p className="eyebrow">Approval</p><h2>Exact-version review</h2></div>
        <button type="button" onClick={() => void refresh()} disabled={loading || pending !== null}>Refresh</button>
      </div>
      <p className="approval-copy">
        Decisions are locked to <strong>{currentArtifact.versionNumber ? `v${currentArtifact.versionNumber}` : "this exact version"}</strong>. A newer version never inherits this decision.
      </p>
      <code className="approval-version-id">{currentArtifact.artifactVersionId}</code>

      {notice ? <div className="approval-notice" role="status">{notice}</div> : null}
      {loading ? <p className="approval-muted">Loading approvals…</p> : null}

      {!loading && !active && canRequest ? (
        <button className="approval-request" type="button" onClick={requestApproval} disabled={pending !== null}>
          {pending === "request" ? "Requesting…" : "Request approval for this exact version"}
        </button>
      ) : null}
      {!loading && !active && !canRequest ? <p className="approval-muted">You can view decisions, but you cannot request approval.</p> : null}

      {active ? (
        <article className="approval-card is-pending">
          <div className="approval-card-top"><strong>{active.title}</strong><span>{active.status}</span></div>
          <p>{active.summary}</p>
          <div className="approval-meta">
            <span>{active.subjectVersionRef}</span>
            <span>Policy {active.policyMode} v{active.policyVersion}</span>
            {active.expiresAt ? <time dateTime={active.expiresAt}>Expires {formatTime(active.expiresAt)}</time> : null}
          </div>
          {canDecide ? (
            <>
              <label className="approval-feedback-label" htmlFor={`approval-feedback-${active.id}`}>Feedback for reject / changes</label>
              <textarea
                id={`approval-feedback-${active.id}`}
                value={feedback}
                onChange={(event) => setFeedback(event.target.value)}
                rows={3}
                maxLength={4_000}
                placeholder="What should change? Optional for Approve."
                disabled={pending !== null}
              />
              <div className="approval-actions">
                <button type="button" onClick={() => void decide("APPROVED")} disabled={pending !== null}>{pending === "APPROVED" ? "Approving…" : "Approve"}</button>
                <button type="button" onClick={() => void decide("CHANGES_REQUESTED")} disabled={pending !== null}>{pending === "CHANGES_REQUESTED" ? "Saving…" : "Request changes"}</button>
                <button type="button" onClick={() => void decide("REJECTED")} disabled={pending !== null}>{pending === "REJECTED" ? "Rejecting…" : "Reject"}</button>
              </div>
            </>
          ) : <p className="approval-muted">This approval requires <code>{active.requiredPermission}</code>. You do not have that permission.</p>}
        </article>
      ) : null}

      {exact.filter((item) => item.status !== "PENDING").length ? (
        <div className="approval-history">
          <span className="eyebrow">Decision history</span>
          {exact.filter((item) => item.status !== "PENDING").map((item) => (
            <div key={item.id} className={`approval-history-row status-${item.status.toLowerCase()}`}>
              <div><strong>{item.status.replaceAll("_", " ")}</strong><small>{item.subjectVersionRef}</small></div>
              <time dateTime={item.resolvedAt ?? item.updatedAt}>{formatTime(item.resolvedAt ?? item.updatedAt)}</time>
            </div>
          ))}
        </div>
      ) : null}

      {approvals.some((item) => item.status === "PENDING" && item.artifactVersionId !== currentArtifact.artifactVersionId) ? (
        <p className="approval-muted">Other exact versions in this project also have pending reviews. They are intentionally not applied to the version open here.</p>
      ) : null}
    </section>
  );
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}
function message(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.detail || error.title || fallback;
  return error instanceof Error ? error.message : fallback;
}
