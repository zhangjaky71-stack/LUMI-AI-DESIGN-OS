"use client";

import { useEffect, useMemo, useState } from "react";
import { useShell } from "@/components/app-shell/shell-context";
import { createAdminGateway } from "@/lib/admin-console/admin-gateway";
import {
  formatBasisPoints,
  formatMicrousd,
  hasAdminPermission,
  safeAdminError,
  sensitiveAction,
} from "@/lib/admin-console/contracts";
import type {
  AdminBootstrap,
  AdminRegistryItem,
  AdminWorkspace,
  RevealedPii,
  ViewAsSession,
} from "@/lib/admin-console/types";
import styles from "./admin-console.module.css";

type Tab =
  | "overview"
  | "users"
  | "runs"
  | "providers"
  | "queue"
  | "registry"
  | "billing"
  | "audit";
type Pending =
  | { kind: "retry"; id: string; summary: string; scope: string }
  | { kind: "cancel"; id: string; summary: string; scope: string }
  | { kind: "provider"; id: string; summary: string; scope: string }
  | { kind: "queue"; id: string; summary: string; scope: string }
  | {
      kind: "registry";
      id: string;
      item: AdminRegistryItem;
      enabled: boolean;
      summary: string;
      scope: string;
    }
  | {
      kind: "billing";
      id: string;
      delta: number;
      summary: string;
      scope: string;
    };

const TABS: readonly { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "users", label: "Users & Orgs" },
  { id: "runs", label: "Runs" },
  { id: "providers", label: "Providers" },
  { id: "queue", label: "Queue" },
  { id: "registry", label: "Registry" },
  { id: "billing", label: "Billing" },
  { id: "audit", label: "Audit" },
];

export function AdminConsole({
  bootstrap,
}: Readonly<{ bootstrap: AdminBootstrap }>) {
  const { api } = useShell();
  const gateway = useMemo(
    () => createAdminGateway(bootstrap, api),
    [api, bootstrap],
  );
  const [workspace, setWorkspace] = useState<AdminWorkspace | null>(
    bootstrap.workspace,
  );
  const [tab, setTab] = useState<Tab>("overview");
  const [pending, setPending] = useState<Pending | null>(null);
  const [reason, setReason] = useState("");
  const [ticket, setTicket] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revealed, setRevealed] = useState<RevealedPii | null>(null);
  const [viewAs, setViewAs] = useState<ViewAsSession | null>(null);

  async function refresh(): Promise<void> {
    setWorkspace(await gateway.load());
  }

  useEffect(() => {
    if (workspace) return;
    const controller = new AbortController();
    gateway
      .load(controller.signal)
      .then(setWorkspace)
      .catch((value) => setError(safeAdminError(value)));
    return () => controller.abort();
  }, [gateway, workspace]);

  async function executePending(): Promise<void> {
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      const input = sensitiveAction(
        pending.summary,
        pending.scope,
        reason,
        ticket,
        confirmText,
      );
      if (pending.kind === "retry") await gateway.retryRun(pending.id, input);
      if (pending.kind === "cancel") await gateway.cancelRun(pending.id, input);
      if (pending.kind === "provider") {
        await gateway.disableProvider(
          pending.id,
          new Date(Date.now() + 60 * 60_000).toISOString(),
          input,
        );
      }
      if (pending.kind === "queue") await gateway.requeue(pending.id, input);
      if (pending.kind === "registry") {
        await gateway.setRegistryEnabled(
          pending.item,
          pending.enabled,
          input,
        );
      }
      if (pending.kind === "billing") {
        await gateway.adjustBilling(pending.id, pending.delta, input);
      }
      await refresh();
      setPending(null);
      setReason("");
      setTicket("");
      setConfirmText("");
    } catch (value) {
      setError(safeAdminError(value));
    } finally {
      setBusy(false);
    }
  }

  async function revealPii(userId: string): Promise<void> {
    if (!reason.trim() || !ticket.trim()) {
      setError("Reason and ticket are required before PII reveal.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setRevealed(await gateway.revealPii(userId, reason, ticket));
    } catch (value) {
      setError(safeAdminError(value));
    } finally {
      setBusy(false);
    }
  }

  async function startView(
    userId: string,
    organizationId: string,
  ): Promise<void> {
    if (!reason.trim() || !ticket.trim()) {
      setError("Reason and ticket are required before View-as.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setViewAs(
        await gateway.startViewAs(userId, organizationId, reason, ticket),
      );
    } catch (value) {
      setError(safeAdminError(value));
    } finally {
      setBusy(false);
    }
  }

  if (!workspace) {
    return (
      <section className={styles.shell}>
        <p>{error ?? "Loading platform operations…"}</p>
      </section>
    );
  }
  const permission = (value: string) => hasAdminPermission(workspace, value);

  return (
    <section className={styles.shell} aria-label="Platform Admin Console">
      {viewAs ? (
        <div className={styles.viewBanner} role="status">
          VIEW-AS · READ ONLY · {viewAs.target_user_id} /{" "}
          {viewAs.target_organization_id} · expires{" "}
          {new Date(viewAs.expires_at).toLocaleTimeString()}
        </div>
      ) : null}
      <header className={styles.header}>
        <div>
          <span className={styles.eyebrow}>PLATFORM ADMIN</span>
          <h1>Operations Console</h1>
          <p>
            受控运维入口。租户管理员权限不会自动获得平台权限，危险动作不允许绕过
            service / confirmation / audit。
          </p>
        </div>
        <div className={styles.roles}>
          {workspace.actor.roles.map((role) => (
            <span key={role}>{role}</span>
          ))}
        </div>
      </header>
      {error ? (
        <div className={styles.error} role="alert">
          {error}
        </div>
      ) : null}
      <nav className={styles.tabs} aria-label="Admin sections">
        {TABS.map((item) => (
          <button
            key={item.id}
            data-active={tab === item.id}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {tab === "overview" ? (
        <div className={styles.metricGrid}>
          <Metric
            label="Active users"
            value={workspace.overview.active_users.toLocaleString()}
          />
          <Metric
            label="Active orgs"
            value={workspace.overview.active_organizations.toLocaleString()}
          />
          <Metric
            label="Daily generations"
            value={workspace.overview.daily_generations.toLocaleString()}
          />
          <Metric
            label="Failure rate"
            value={formatBasisPoints(
              workspace.overview.failure_rate_basis_points,
            )}
          />
          <Metric
            label="Provider health"
            value={workspace.overview.provider_health}
          />
          <Metric
            label="Queue depth"
            value={workspace.overview.queue_depth.toLocaleString()}
          />
          <Metric
            label="Cost today"
            value={formatMicrousd(workspace.overview.cost_today_microusd)}
          />
          <article className={styles.card}>
            <span className={styles.label}>Critical alerts</span>
            {workspace.overview.critical_alerts.length ? (
              workspace.overview.critical_alerts.map((value) => (
                <strong key={value}>{value}</strong>
              ))
            ) : (
              <strong>None</strong>
            )}
          </article>
        </div>
      ) : null}

      {tab === "users" ? (
        <div className={styles.list}>
          {workspace.users.map((user) => (
            <article className={styles.card} key={user.user_id}>
              <div className={styles.row}>
                <div>
                  <strong>{user.display_name}</strong>
                  <p className={styles.mono}>{user.user_id}</p>
                </div>
                <span className={styles.state}>{user.status}</span>
              </div>
              <p>
                {user.email_masked ?? "No email"} ·{" "}
                {user.phone_masked ?? "No phone"}
              </p>
              <p>
                Orgs: {user.organization_ids.join(", ")} · Roles:{" "}
                {user.membership_roles.join(", ")}
              </p>
              {user.recent_error_codes.length ? (
                <p>Recent errors: {user.recent_error_codes.join(", ")}</p>
              ) : null}
              <div className={styles.actions}>
                {permission("admin.privacy.execute") ? (
                  <button
                    disabled={busy}
                    onClick={() => void revealPii(user.user_id)}
                  >
                    Reveal PII
                  </button>
                ) : null}
                <button
                  disabled={busy || !user.organization_ids[0]}
                  onClick={() =>
                    void startView(
                      user.user_id,
                      user.organization_ids[0] ?? "",
                    )
                  }
                >
                  View-as readonly
                </button>
              </div>
              {revealed?.user_id === user.user_id ? (
                <div className={styles.sensitive}>
                  PII REVEALED · {revealed.email ?? "—"} ·{" "}
                  {revealed.phone ?? "—"}
                </div>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}

      {tab === "runs" ? (
        <div className={styles.list}>
          {workspace.runs.map((run) => (
            <article className={styles.card} key={run.run_id}>
              <div className={styles.row}>
                <strong>{run.run_id}</strong>
                <span className={styles.state}>{run.status}</span>
              </div>
              <p>
                {run.kind} · {run.organization_id} ·{" "}
                {run.provider ?? run.tool ?? "—"}
              </p>
              <p>
                Error: {run.error_code ?? "—"} · Cost:{" "}
                {formatMicrousd(run.cost_microusd)}
              </p>
              {permission("admin.user.manage_limited") ? (
                <div className={styles.actions}>
                  {run.retryable ? (
                    <button
                      onClick={() =>
                        setPending({
                          kind: "retry",
                          id: run.run_id,
                          summary: `Retry run ${run.run_id}`,
                          scope: `run:${run.run_id}`,
                        })
                      }
                    >
                      Retry with confirmation
                    </button>
                  ) : null}
                  {run.cancellable ? (
                    <button
                      onClick={() =>
                        setPending({
                          kind: "cancel",
                          id: run.run_id,
                          summary: `Cancel run ${run.run_id}`,
                          scope: `run:${run.run_id}`,
                        })
                      }
                    >
                      Cancel with confirmation
                    </button>
                  ) : null}
                </div>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}

      {tab === "providers" ? (
        <div className={styles.list}>
          {workspace.providers.map((provider) => (
            <article className={styles.card} key={provider.provider_id}>
              <div className={styles.row}>
                <strong>{provider.provider_id}</strong>
                <span className={styles.state}>{provider.health}</span>
              </div>
              <p>
                Circuit {provider.circuit} · Synthetic {provider.synthetic_health} ·
                Routing {formatBasisPoints(provider.routing_weight_basis_points)}
              </p>
              <p>Pricing snapshot: {provider.pricing_snapshot_id ?? "unknown"}</p>
              {permission("admin.provider.manage") ? (
                <button
                  disabled={provider.health === "DISABLED"}
                  onClick={() =>
                    setPending({
                      kind: "provider",
                      id: provider.provider_id,
                      summary: `Temporarily disable provider ${provider.provider_id}`,
                      scope: `provider:${provider.provider_id}`,
                    })
                  }
                >
                  Disable 1 hour
                </button>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}

      {tab === "queue" ? (
        <div className={styles.list}>
          {workspace.queue.map((item) => (
            <article className={styles.card} key={item.queue_item_id}>
              <div className={styles.row}>
                <strong>{item.queue_item_id}</strong>
                <span className={styles.state}>{item.state}</span>
              </div>
              <p>
                {item.task_id} · attempts {item.attempts} ·{" "}
                {item.last_error_code ?? "No error"}
              </p>
              <p className={styles.mono}>
                Payload ref: {item.payload_ref}
                <br />
                SHA256: {item.payload_sha256}
              </p>
              {permission("admin.queue.requeue") &&
              (item.state === "DLQ" || item.state === "STUCK") ? (
                <button
                  onClick={() =>
                    setPending({
                      kind: "queue",
                      id: item.queue_item_id,
                      summary: `Requeue item ${item.queue_item_id}`,
                      scope: `queue-item:${item.queue_item_id}`,
                    })
                  }
                >
                  Requeue original payload
                </button>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}

      {tab === "registry" ? (
        <div className={styles.list}>
          {workspace.registry.map((item) => (
            <article
              className={styles.card}
              key={`${item.kind}:${item.registry_id}`}
            >
              <div className={styles.row}>
                <strong>
                  {item.name} · {item.version}
                </strong>
                <span className={styles.state}>
                  {item.enabled ? "ENABLED" : "DISABLED"}
                </span>
              </div>
              <p>
                {item.kind} · traffic {formatBasisPoints(item.traffic_basis_points)}
              </p>
              <p>Read-only deploy diff: {item.deploy_diff_summary}</p>
              <button
                onClick={() =>
                  setPending({
                    kind: "registry",
                    id: item.registry_id,
                    item,
                    enabled: !item.enabled,
                    summary: `${item.enabled ? "Disable" : "Enable"} ${item.kind.toLowerCase()} ${item.registry_id}`,
                    scope: `${item.kind.toLowerCase()}:${item.registry_id}`,
                  })
                }
              >
                {item.enabled ? "Disable" : "Enable"} via registry service
              </button>
            </article>
          ))}
        </div>
      ) : null}

      {tab === "billing" ? (
        <div className={styles.list}>
          <article className={styles.card}>
            <h2>Billing support</h2>
            <p>
              Subscription / invoice provider state is read-only. Credit correction
              is an immutable NODE-63 ADJUSTMENT ledger entry.
            </p>
            {permission("admin.billing.adjust") ? (
              <button
                onClick={() =>
                  setPending({
                    kind: "billing",
                    id: "org-lumi",
                    delta: 100,
                    summary: "Adjust billing credits by 100",
                    scope: "organization:org-lumi",
                  })
                }
              >
                Grant +100 credits to org-lumi
              </button>
            ) : (
              <p>BILLING_ADMIN permission required.</p>
            )}
          </article>
        </div>
      ) : null}

      {tab === "audit" ? (
        <div className={styles.list}>
          {workspace.audit.length ? (
            workspace.audit.map((event) => (
              <article className={styles.card} key={event.event_id}>
                <div className={styles.row}>
                  <strong>{event.event_type}</strong>
                  <span>{event.ticket_ref}</span>
                </div>
                <p>
                  {event.actor_id} → {event.target_type}:{event.target_id}
                </p>
                <p>{event.reason}</p>
              </article>
            ))
          ) : (
            <article className={styles.card}>
              <p>NODE-65 durable Audit pipeline integration pending.</p>
            </article>
          )}
        </div>
      ) : null}

      <aside className={styles.guardrail}>
        <strong>Guardrails</strong>
        <span>
          No arbitrary SQL · no kill-process button · no queue payload editor · no
          direct payment-provider state mutation.
        </span>
        <span>
          PII is masked by default. View-as is readonly. Provider disable is
          temporary.
        </span>
      </aside>

      <div className={styles.supportFields}>
        <label>
          Reason
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Why is access/action needed?"
          />
        </label>
        <label>
          Ticket / reference
          <input
            value={ticket}
            onChange={(event) => setTicket(event.target.value)}
            placeholder="INC-123 / SUP-456"
          />
        </label>
      </div>

      {pending ? (
        <div className={styles.backdrop}>
          <div
            className={styles.dialog}
            role="dialog"
            aria-modal="true"
            aria-label="Confirm sensitive admin action"
          >
            <span className={styles.eyebrow}>SENSITIVE ACTION</span>
            <h2>{pending.summary}</h2>
            <p>
              Impact scope: <code>{pending.scope}</code>
            </p>
            <p>
              Reason: {reason || "Missing"} · Ticket: {ticket || "Missing"}
            </p>
            <label>
              Second confirmation
              <input
                autoFocus
                value={confirmText}
                onChange={(event) => setConfirmText(event.target.value)}
                placeholder="Type CONFIRM"
              />
            </label>
            <div className={styles.actions}>
              <button onClick={() => setPending(null)}>Cancel</button>
              <button
                disabled={
                  busy ||
                  confirmText !== "CONFIRM" ||
                  !reason.trim() ||
                  !ticket.trim()
                }
                onClick={() => void executePending()}
              >
                Confirm action
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function Metric({
  label,
  value,
}: Readonly<{ label: string; value: string }>) {
  return (
    <article className={styles.card}>
      <span className={styles.label}>{label}</span>
      <strong className={styles.metric}>{value}</strong>
    </article>
  );
}
