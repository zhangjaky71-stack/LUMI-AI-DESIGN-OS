"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import styles from "./approval-center.module.css";
import { createApprovalGateway } from "@/lib/approval-ui/approval-gateway";
import { historyApprovals, pendingApprovals, policyLabel, safeApprovalError } from "@/lib/approval-ui/contracts";
import type { ApprovalBootstrap, ApprovalDecision, ApprovalRecord, ApprovalWorkspace } from "@/lib/approval-ui/types";

export function ApprovalCenter({ projectId, bootstrap }: { projectId: string; bootstrap: ApprovalBootstrap }) {
  const gateway = useMemo(() => createApprovalGateway(bootstrap), [bootstrap]);
  const [workspace, setWorkspace] = useState<ApprovalWorkspace | null>(bootstrap.workspace);
  const [tab, setTab] = useState<"PENDING" | "HISTORY">("PENDING");
  const [busy, setBusy] = useState<string | null>(null);
  const [changesFor, setChangesFor] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState<{ message: string; request_id: string | null } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    gateway.load(projectId, controller.signal).then(setWorkspace).catch((value) => {
      if (!controller.signal.aborted) setError(safeApprovalError(value));
    });
    return () => controller.abort();
  }, [gateway, projectId]);

  async function decide(approval: ApprovalRecord, decision: ApprovalDecision): Promise<void> {
    setBusy(approval.approval_id);
    setError(null);
    try {
      const updated = await gateway.decide(projectId, approval.approval_id, {
        decision,
        feedback: decision === "REQUEST_CHANGES" ? {
          comment: feedback,
          node_refs: [],
          region_refs: [],
          requested_changes: feedback.trim() ? [feedback.trim()] : [],
        } : null,
      });
      setWorkspace((current) => current ? {
        ...current,
        approvals: current.approvals.map((item) => item.approval_id === updated.approval_id ? updated : item),
      } : current);
      setChangesFor(null);
      setFeedback("");
    } catch (value) {
      setError(safeApprovalError(value));
    } finally {
      setBusy(null);
    }
  }

  if (!workspace) {
    return <main className={styles.page}><div className={styles.loading}>Loading canonical approvals…</div></main>;
  }
  const pending = pendingApprovals(workspace);
  const history = historyApprovals(workspace);
  const items = tab === "PENDING" ? pending : history;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <Link href={`/app/projects/${encodeURIComponent(projectId)}`} className={styles.back}>← Project</Link>
          <p className={styles.eyebrow}>NODE-62 · HUMAN-IN-THE-LOOP</p>
          <h1>Approval Center</h1>
          <p className={styles.lede}>Decisions are locked to an exact subject version. A newer ArtifactVersion never inherits an older approval.</p>
        </div>
        <div className={styles.summary}>
          <strong>{pending.length}</strong><span>waiting</span>
          <strong>{history.length}</strong><span>history</span>
        </div>
      </header>

      <section className={styles.truth} data-testid="approval-truth-boundary">
        <b>Canonical decision boundary</b>
        <span>Server permission + exact version + status + expiry + run-resume checks execute atomically before Graph resume.</span>
      </section>

      <nav className={styles.tabs} aria-label="Approval filters">
        <button className={tab === "PENDING" ? styles.activeTab : ""} onClick={() => setTab("PENDING")}>Waiting <span>{pending.length}</span></button>
        <button className={tab === "HISTORY" ? styles.activeTab : ""} onClick={() => setTab("HISTORY")}>History <span>{history.length}</span></button>
      </nav>

      {error && <div className={styles.error} role="alert">{error.message}{error.request_id && <small>Request {error.request_id}</small>}</div>}

      <section className={styles.list}>
        {items.length === 0 && <div className={styles.empty}>No approvals in this view.</div>}
        {items.map((approval) => {
          const waiting = approval.status === "PENDING";
          const actionDisabled = !workspace.can_decide || busy === approval.approval_id;
          return (
            <article key={approval.approval_id} className={styles.card} data-testid={`approval-${approval.approval_id}`}>
              <div className={styles.cardTop}>
                <div><span className={styles.type}>{approval.approval_type.replaceAll("_", " ")}</span><h2>{approval.payload_summary}</h2></div>
                <span className={`${styles.status} ${styles[`status${approval.status}`]}`}>{approval.status.replaceAll("_", " ")}</span>
              </div>
              <div className={styles.subject} data-testid="exact-subject">
                <span>Exact subject</span>
                <code>{approval.subject.subject_type} / {approval.subject.subject_id}</code>
                <b>{approval.subject.subject_version}</b>
              </div>
              <dl className={styles.meta}>
                <div><dt>Policy</dt><dd>{policyLabel(approval)} · policy v{approval.policy.version}</dd></div>
                <div><dt>Permission</dt><dd>{approval.policy.required_permission}</dd></div>
                <div><dt>Requested by</dt><dd>{approval.requested_by}</dd></div>
                <div><dt>Agent run</dt><dd>{approval.agent_run_id ?? "—"}</dd></div>
                <div><dt>Expires</dt><dd>{approval.expires_at ? new Date(approval.expires_at).toLocaleString() : "No expiry"}</dd></div>
                {approval.superseded_by && <div><dt>Superseded by</dt><dd>{approval.superseded_by}</dd></div>}
              </dl>

              {approval.feedback && <div className={styles.feedback}><b>Requested changes</b><p>{approval.feedback.comment}</p>{approval.feedback.requested_changes.map((item) => <span key={item}>• {item}</span>)}</div>}

              {waiting && <div className={styles.actions}>
                <button disabled={actionDisabled} onClick={() => void decide(approval, "APPROVE")} className={styles.primary}>Approve exact version</button>
                <button disabled={actionDisabled} onClick={() => void decide(approval, "REJECT")}>Reject</button>
                <button disabled={actionDisabled} onClick={() => setChangesFor(changesFor === approval.approval_id ? null : approval.approval_id)}>Request changes</button>
              </div>}

              {changesFor === approval.approval_id && waiting && <div className={styles.changeBox}>
                <label htmlFor={`changes-${approval.approval_id}`}>Structured feedback</label>
                <textarea id={`changes-${approval.approval_id}`} value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="Describe the change. Node/region references are preserved by the API when supplied from Canvas." />
                <button disabled={actionDisabled || !feedback.trim()} onClick={() => void decide(approval, "REQUEST_CHANGES")} className={styles.primary}>Send changes to workflow</button>
              </div>}

              <footer className={styles.footer}>
                <span>{approval.decisions.length} decision record{approval.decisions.length === 1 ? "" : "s"}</span>
                {approval.agent_run_id && <Link href={`/app/projects/${encodeURIComponent(projectId)}/workspace`}>Open Agent timeline →</Link>}
              </footer>
            </article>
          );
        })}
      </section>
    </main>
  );
}
