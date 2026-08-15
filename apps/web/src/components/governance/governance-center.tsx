"use client";

import { useEffect, useMemo, useState } from "react";
import { useShell } from "@/components/app-shell/shell-context";
import { createGovernanceGateway } from "@/lib/governance/governance-gateway";
import {
  auditEventLabel,
  canDownload,
  latestRetentionPolicies,
  safeAuditDownloadUrl,
  safeGovernanceError,
} from "@/lib/governance/contracts";
import type {
  AuditDownloadLeaseView,
  AuditFilters,
  AuditResult,
  ExportFormat,
  GovernanceBootstrap,
  GovernanceWorkspace,
  RetentionClass,
} from "@/lib/governance/types";
import styles from "./governance-center.module.css";

type Tab = "audit" | "retention" | "holds" | "deletion" | "exports";

const TABS: readonly { id: Tab; label: string }[] = [
  { id: "audit", label: "Audit" },
  { id: "retention", label: "Retention" },
  { id: "holds", label: "Legal Holds" },
  { id: "deletion", label: "Deletion" },
  { id: "exports", label: "Exports" },
];

export function GovernanceCenter({ bootstrap }: Readonly<{ bootstrap: GovernanceBootstrap }>) {
  const { api, activeOrganization } = useShell();
  const gateway = useMemo(
    () => createGovernanceGateway(bootstrap, api, activeOrganization.id),
    [activeOrganization.id, api, bootstrap],
  );
  const [workspace, setWorkspace] = useState<GovernanceWorkspace | null>(bootstrap.workspace);
  const [tab, setTab] = useState<Tab>("audit");
  const [action, setAction] = useState("");
  const [result, setResult] = useState<AuditResult | "">("");
  const [resource, setResource] = useState("");
  const [trace, setTrace] = useState("");
  const [reason, setReason] = useState("");
  const [ticket, setTicket] = useState("");
  const [scopeId, setScopeId] = useState("");
  const [subjectUserId, setSubjectUserId] = useState("");
  const [policyClass, setPolicyClass] = useState<RetentionClass>("CONTENT");
  const [policyDays, setPolicyDays] = useState("365");
  const [policyNote, setPolicyNote] = useState("");
  const [lease, setLease] = useState<AuditDownloadLeaseView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (workspace) return;
    const controller = new AbortController();
    gateway
      .load(controller.signal)
      .then(setWorkspace)
      .catch((value) => setError(safeGovernanceError(value)));
    return () => controller.abort();
  }, [gateway, workspace]);

  const filters: AuditFilters = {
    action: action.trim() || undefined,
    result: result || undefined,
    resource_id: resource.trim() || undefined,
    trace_id: trace.trim() || undefined,
  };

  async function refresh(): Promise<void> {
    setWorkspace(await gateway.load());
  }

  async function run(operation: () => Promise<unknown>): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await operation();
      await refresh();
    } catch (value) {
      setError(safeGovernanceError(value));
    } finally {
      setBusy(false);
    }
  }

  async function search(reset = true): Promise<void> {
    if (!workspace) return;
    setBusy(true);
    setError(null);
    try {
      const page = await gateway.searchAudit(
        reset ? filters : { ...filters, cursor: workspace.audit.next_cursor ?? undefined },
      );
      setWorkspace({
        ...workspace,
        audit: reset
          ? page
          : { items: [...workspace.audit.items, ...page.items], next_cursor: page.next_cursor },
      });
    } catch (value) {
      setError(safeGovernanceError(value));
    } finally {
      setBusy(false);
    }
  }

  async function publishRetention(): Promise<void> {
    if (!workspace) return;
    const days = Number.parseInt(policyDays, 10);
    if (!Number.isInteger(days) || days < 1 || days > 36500 || !policyNote.trim()) {
      setError("Retention days (1–36500) and a policy note are required.");
      return;
    }
    const current = latestRetentionPolicies(workspace.retention_policies).find(
      (item) => item.retention_class === policyClass,
    );
    await run(() => gateway.publishRetention(policyClass, (current?.version ?? 0) + 1, days, policyNote.trim()));
    setPolicyNote("");
  }

  async function createHold(): Promise<void> {
    if (!scopeId.trim() || !reason.trim() || !ticket.trim()) {
      setError("Scope, reason and ticket are required for a legal hold.");
      return;
    }
    await run(() => gateway.createHold("USER", scopeId.trim(), reason.trim(), ticket.trim()));
    setScopeId("");
  }

  async function requestDeletion(): Promise<void> {
    if (!subjectUserId.trim()) {
      setError("Subject user ID is required for a deletion request.");
      return;
    }
    await run(() => gateway.requestDeletion(subjectUserId.trim()));
  }

  async function createExport(format: ExportFormat): Promise<void> {
    await run(() => gateway.createExport(format, filters));
  }

  async function freshDownload(jobId: string): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      setLease(await gateway.getDownload(jobId));
    } catch (value) {
      setError(safeGovernanceError(value));
    } finally {
      setBusy(false);
    }
  }

  if (!workspace) {
    return <section className={styles.shell}><p>{error ?? "Loading governance…"}</p></section>;
  }

  const latestPolicies = latestRetentionPolicies(workspace.retention_policies);
  const selectedPolicy = latestPolicies.find((item) => item.retention_class === policyClass);
  const downloadUrl = safeAuditDownloadUrl(lease);

  return (
    <section className={styles.shell} aria-label="Audit and Governance Center">
      <header className={styles.header}>
        <div>
          <span className={styles.eyebrow}>GOVERNANCE</span>
          <h1>Audit, Retention & Data Governance</h1>
          <p>Append-only 审计、版本化保留策略、Legal Hold、数据删除和审计导出。业务日志不等于 Audit truth。</p>
        </div>
        <div className={styles.truth}><strong>{workspace.organization_id}</strong><span>Tenant scoped</span></div>
      </header>
      {error ? <div className={styles.error} role="alert">{error}</div> : null}
      <nav className={styles.tabs} aria-label="Governance sections">
        {TABS.map((item) => (
          <button key={item.id} type="button" data-active={tab === item.id} onClick={() => setTab(item.id)}>
            {item.label}
          </button>
        ))}
      </nav>

      {tab === "audit" ? (
        <>
          <div className={styles.filters}>
            <label>Action<input value={action} onChange={(event) => setAction(event.target.value)} placeholder="ARTIFACT_APPROVED" /></label>
            <label>Result<select value={result} onChange={(event) => setResult(event.target.value as AuditResult | "")}><option value="">All</option><option>SUCCESS</option><option>DENIED</option><option>FAILED</option></select></label>
            <label>Resource ID<input value={resource} onChange={(event) => setResource(event.target.value)} placeholder="artifact-v4" /></label>
            <label>Trace ID<input value={trace} onChange={(event) => setTrace(event.target.value)} placeholder="trace-…" /></label>
            <button disabled={busy} type="button" onClick={() => void search(true)}>Search audit</button>
          </div>
          <div className={styles.list}>
            {workspace.audit.items.map((event) => (
              <article className={styles.card} key={event.event_id}>
                <div className={styles.row}><strong>{auditEventLabel(event.action)}</strong><span className={styles.state}>{event.result}</span></div>
                <p>{event.actor_type} · {event.actor_id}{event.actor_version ? ` @ ${event.actor_version}` : ""}</p>
                <p>{event.resource_type}:{event.resource_id}{event.resource_version ? ` · ${event.resource_version}` : ""}</p>
                <div className={styles.meta}><span>{event.reason_code}</span><span>{new Date(event.occurred_at).toLocaleString()}</span><code>{event.trace_id ?? event.request_id ?? "no trace"}</code></div>
                <small>Retention {event.retention_class} · policy v{event.retention_policy_version} · hash {event.event_hash.slice(0, 12)}…</small>
              </article>
            ))}
          </div>
          {workspace.audit.next_cursor ? <button disabled={busy} type="button" onClick={() => void search(false)}>Load more</button> : null}
        </>
      ) : null}

      {tab === "retention" ? (
        <div className={styles.columns}>
          <article className={styles.card}>
            <h2>Retention policy versions</h2>
            <p className={styles.notice}>这些天数是工程默认值，不代表任何地区的法律结论；生产上线前必须经过适用法域的法律/合规审查。</p>
            {latestPolicies.map((policy) => <div className={styles.row} key={policy.retention_class}><span>{policy.retention_class} · v{policy.version}</span><strong>{policy.retention_days} days</strong></div>)}
            {workspace.capabilities.can_manage_retention ? <div className={styles.item}>
              <h3>Publish next immutable version</h3>
              <label>Retention class<select value={policyClass} onChange={(event) => setPolicyClass(event.target.value as RetentionClass)}>{latestPolicies.map((policy) => <option key={policy.retention_class} value={policy.retention_class}>{policy.retention_class}</option>)}</select></label>
              <label>Retention days<input inputMode="numeric" value={policyDays} onChange={(event) => setPolicyDays(event.target.value)} /></label>
              <label>Policy note<input value={policyNote} onChange={(event) => setPolicyNote(event.target.value)} placeholder="Reason / policy reference" /></label>
              <span>Next exact version: v{(selectedPolicy?.version ?? 0) + 1}</span>
              <button disabled={busy || !policyNote.trim()} type="button" onClick={() => void publishRetention()}>Publish next version</button>
            </div> : null}
          </article>
          <article className={styles.card}>
            <h2>Eligible candidates</h2>
            <p>Legal/Billing Hold 命中的资源不会进入 GC candidate。</p>
            {workspace.retention_candidates.length ? workspace.retention_candidates.map((candidate) => <div className={styles.item} key={`${candidate.resource.resource_type}:${candidate.resource.resource_id}`}><strong>{candidate.resource.resource_type}:{candidate.resource.resource_id}</strong><span>{candidate.resource.retention_class} · policy v{candidate.policy_version}</span><span>Eligible {new Date(candidate.eligible_at).toLocaleDateString()}</span></div>) : <p>No currently eligible resources.</p>}
          </article>
        </div>
      ) : null}

      {tab === "holds" ? (
        <div className={styles.columns}>
          <article className={styles.card}>
            <h2>Active holds</h2>
            {workspace.legal_holds.length ? workspace.legal_holds.map((hold) => <div className={styles.item} key={hold.hold_id}><div className={styles.row}><strong>{hold.hold_type} · {hold.scope_type}:{hold.scope_id}</strong><span>{hold.ticket_ref}</span></div><span>{hold.reason_code}</span>{workspace.capabilities.can_manage_holds ? <button disabled={busy || !reason.trim() || !ticket.trim()} type="button" onClick={() => void run(() => gateway.releaseHold(hold.hold_id, reason, ticket))}>Release with reason + ticket</button> : null}</div>) : <p>No active holds.</p>}
          </article>
          <article className={styles.card}>
            <h2>Create legal hold</h2>
            <p>高权限动作。Hold 只暂停受影响资源的删除/GC，不修改原 Audit Event。</p>
            <label>User scope ID<input value={scopeId} onChange={(event) => setScopeId(event.target.value)} placeholder="user-id" /></label>
            <label>Reason code<input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="LITIGATION" /></label>
            <label>Ticket<input value={ticket} onChange={(event) => setTicket(event.target.value)} placeholder="LEGAL-123" /></label>
            <button disabled={busy || !workspace.capabilities.can_manage_holds} type="button" onClick={() => void createHold()}>Create hold</button>
          </article>
        </div>
      ) : null}

      {tab === "deletion" ? (
        <div className={styles.columns}>
          <article className={styles.card}>
            <h2>Deletion workflow</h2>
            <p>流程：scope → hold check → deactivate → delete/anonymize → object GC → search/vector removal → completion record。</p>
            <label>Subject user ID<input value={subjectUserId} onChange={(event) => setSubjectUserId(event.target.value)} placeholder="user-id" /></label>
            <button disabled={busy || !workspace.capabilities.can_manage_deletion} type="button" onClick={() => void requestDeletion()}>Request deletion</button>
          </article>
          <article className={styles.card}>
            <h2>Requests</h2>
            {workspace.deletions.length ? workspace.deletions.map((item) => <div className={styles.item} key={item.request_id}><div className={styles.row}><strong>{item.request_id}</strong><span className={styles.state}>{item.status}</span></div><span>{item.subject_user_id} · resources {item.resource_refs.length}</span>{item.blocked_hold_ids.length ? <span className={styles.warning}>Blocked by {item.blocked_hold_ids.join(", ")}</span> : null}<span>deleted {item.deleted_count} · anonymized {item.anonymized_count} · retained {item.retained_count}</span>{workspace.capabilities.can_manage_deletion && !["COMPLETED", "DELETING"].includes(item.status) ? <button disabled={busy} type="button" onClick={() => void run(() => gateway.executeDeletion(item.request_id))}>Execute workflow</button> : null}</div>) : <p>No deletion requests.</p>}
          </article>
        </div>
      ) : null}

      {tab === "exports" ? (
        <div className={styles.columns}>
          <article className={styles.card}>
            <h2>Create audit export</h2>
            <p>大型导出由异步 job 生成。持久化的是 object ref / checksum / size；signed URL 只在下载响应中短时返回。</p>
            <div className={styles.actions}><button disabled={busy || !workspace.capabilities.can_export_audit} onClick={() => void createExport("JSON")}>Export JSON</button><button disabled={busy || !workspace.capabilities.can_export_audit} onClick={() => void createExport("CSV")}>Export CSV</button></div>
            {downloadUrl && lease ? <a className={styles.download} href={downloadUrl} rel="noreferrer">Open fresh signed download · expires {new Date(lease.expires_at).toLocaleTimeString()} →</a> : null}
          </article>
          <article className={styles.card}>
            <h2>Export jobs</h2>
            {workspace.exports.length ? workspace.exports.map((job) => <div className={styles.item} key={job.job_id}><div className={styles.row}><strong>{job.export_format} · {job.job_id}</strong><span className={styles.state}>{job.status}</span></div><span>{job.file_name ?? "Preparing file"}</span>{job.checksum_sha256 ? <code>sha256 {job.checksum_sha256.slice(0, 16)}…</code> : null}{job.size_bytes !== null ? <span>{job.size_bytes.toLocaleString()} bytes</span> : null}{canDownload(job) ? <button disabled={busy} type="button" onClick={() => void freshDownload(job.job_id)}>Get fresh download</button> : null}</div>) : <p>No export jobs.</p>}
          </article>
        </div>
      ) : null}

      <footer className={styles.guardrail}>
        <strong>Truth boundaries</strong>
        <span>Audit is append-only. Correction creates a new event. Signed download URLs are never canonical state.</span>
        <span>Deletion does not erase retained Audit/Billing evidence while retention or hold policy requires it.</span>
      </footer>
    </section>
  );
}
