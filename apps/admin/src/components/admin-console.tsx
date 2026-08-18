"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  AdminApiError,
  discardDeadLetter,
  loadAdminDashboard,
  loadAdminPrincipal,
  loadDeadLetters,
  loadFailingRuns,
  loadFeatureFlags,
  loadProviders,
  replayDeadLetter,
  setProviderOverride,
} from "@/lib/admin/api";
import type {
  AdminDashboard,
  FeatureFlag,
  PlatformAdminPrincipal,
  ProviderControlSummary,
  SafeDeadLetter,
  SafeRunSummary,
} from "@/lib/admin/types";

type ConsoleData = {
  principal: PlatformAdminPrincipal;
  dashboard: AdminDashboard;
  runs: SafeRunSummary[];
  deadLetters: SafeDeadLetter[];
  providers: ProviderControlSummary[];
  flags: FeatureFlag[];
};

const BOOTSTRAP_ORG = process.env.NEXT_PUBLIC_LUMI_ADMIN_ORGANIZATION_ID ?? "";

function shortId(value: string): string {
  return value.length <= 14 ? value : `${value.slice(0, 8)}…${value.slice(-4)}`;
}

function stamp(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function errorMessage(error: unknown): string {
  if (error instanceof AdminApiError) {
    return error.code ? `${error.code}: ${error.message}` : error.message;
  }
  return error instanceof Error ? error.message : "Unknown admin console error";
}

function askReason(title: string): string | null {
  const value = window.prompt(`${title}\n\n请输入至少 8 个字符的操作理由：`)?.trim() ?? "";
  if (value.length < 8) {
    window.alert("操作理由至少需要 8 个字符。此次操作未执行。");
    return null;
  }
  return value;
}

export function AdminConsole() {
  const [organizationId, setOrganizationId] = useState(BOOTSTRAP_ORG);
  const [data, setData] = useState<ConsoleData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  useEffect(() => {
    if (BOOTSTRAP_ORG || typeof window === "undefined") return;
    const saved = window.localStorage.getItem("lumi.admin.organization_id");
    if (saved) setOrganizationId(saved);
  }, []);

  const refresh = useCallback(async () => {
    const org = organizationId.trim();
    if (!org) {
      setError("需要 Organization ID 才能通过现有登录握手进入平台 Admin 控制面。此 ID 不会授予 Admin 权限。");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const principal = await loadAdminPrincipal(org);
      const [dashboard, runs, deadLetters, providers, flags] = await Promise.all([
        loadAdminDashboard(org),
        loadFailingRuns(org),
        loadDeadLetters(org),
        loadProviders(org),
        loadFeatureFlags(org),
      ]);
      setData({ principal, dashboard, runs, deadLetters, providers, flags });
      window.localStorage.setItem("lumi.admin.organization_id", org);
    } catch (caught) {
      setData(null);
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [organizationId]);

  const permissions = useMemo(
    () => new Set(data?.principal.permissions ?? []),
    [data?.principal.permissions],
  );

  const perform = useCallback(
    async (key: string, operation: () => Promise<void>) => {
      setActionBusy(key);
      setError(null);
      try {
        await operation();
        await refresh();
      } catch (caught) {
        setError(errorMessage(caught));
      } finally {
        setActionBusy(null);
      }
    },
    [refresh],
  );

  const onReplay = useCallback(
    (deadLetter: SafeDeadLetter) => {
      const reason = askReason(`Replay DLQ ${shortId(deadLetter.id)}`);
      if (!reason) return;
      void perform(`replay:${deadLetter.id}`, () =>
        replayDeadLetter(organizationId.trim(), deadLetter.id, reason),
      );
    },
    [organizationId, perform],
  );

  const onDiscard = useCallback(
    (deadLetter: SafeDeadLetter) => {
      const reason = askReason(`Discard DLQ ${shortId(deadLetter.id)}`);
      if (!reason) return;
      if (!window.confirm("Discard 会终止该 DLQ 项的后续 replay。确认继续？")) return;
      void perform(`discard:${deadLetter.id}`, () =>
        discardDeadLetter(organizationId.trim(), deadLetter.id, reason),
      );
    },
    [organizationId, perform],
  );

  const onProviderAction = useCallback(
    (provider: ProviderControlSummary, action: "force_disabled" | "clear_override") => {
      const reason = askReason(`${action} ${provider.provider}`);
      if (!reason) return;
      if (action === "force_disabled" && !window.confirm("这是高风险路由变更。确认禁用该 Provider scope？")) {
        return;
      }
      void perform(`${action}:${provider.provider}:${provider.model ?? "*"}`, () =>
        setProviderOverride(organizationId.trim(), {
          provider: provider.provider,
          model: provider.model,
          capability: provider.capability,
          action,
          reason,
        }),
      );
    },
    [organizationId, perform],
  );

  return (
    <div className="admin-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark">L</div>
          <div>
            <strong>LUMI</strong>
            <span>Operations Console</span>
          </div>
        </div>
        <nav aria-label="Admin sections">
          {[
            ["Overview", "Live operating posture"],
            ["Runs", "Failure metadata only"],
            ["Queues / DLQ", "Replay through idempotency"],
            ["Providers", "Health & audited overrides"],
            ["Feature Flags", "Server-side scoped flags"],
            ["Registry", "Release-gated promotion"],
            ["Billing", "Status only in NODE-64"],
            ["Audit", "Append-only control records"],
          ].map(([name, caption], index) => (
            <a className={index === 0 ? "nav-item active" : "nav-item"} href={`#section-${index}`} key={name}>
              <span>{name}</span>
              <small>{caption}</small>
            </a>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="status-dot" />
          Platform RBAC enforced server-side
        </div>
      </aside>

      <main className="console-main">
        <header className="topbar">
          <div>
            <p className="eyebrow">NODE-64 · INTERNAL CONTROL PLANE</p>
            <h1>Admin & Operations</h1>
          </div>
          <div className="context-form">
            <label htmlFor="organization-id">Auth organization context</label>
            <div>
              <input
                id="organization-id"
                value={organizationId}
                onChange={(event) => setOrganizationId(event.target.value)}
                placeholder="UUID"
                spellCheck={false}
              />
              <button onClick={() => void refresh()} disabled={loading} type="button">
                {loading ? "Loading…" : "Connect"}
              </button>
            </div>
          </div>
        </header>

        <section className="security-banner">
          <strong>Organization OWNER is not Platform Admin.</strong>
          <span>
            组织 ID 仅用于复用现有 session authentication；真正授权来自独立 platform_admin_principals。
          </span>
        </section>

        {error ? <div className="error-banner" role="alert">{error}</div> : null}

        {!data ? (
          <section className="empty-state">
            <div className="empty-orbit" />
            <p className="eyebrow">FAIL CLOSED</p>
            <h2>Connect an authenticated platform-admin session</h2>
            <p>
              未验证平台 Admin principal 前不加载运行、队列、Provider、成本或用户相关数据。
            </p>
          </section>
        ) : (
          <>
            <section className="principal-strip" id="section-0">
              <div>
                <span>Signed in as</span>
                <strong>{data.principal.role}</strong>
              </div>
              <div className="permission-list">
                {data.principal.permissions.map((permission) => (
                  <code key={permission}>{permission}</code>
                ))}
              </div>
            </section>

            <section className="metric-grid" aria-label="Operational dashboard">
              {[
                ["Active runs", data.dashboard.active_runs, "in flight"],
                ["Failed runs", data.dashboard.failed_runs, "needs inspection"],
                ["Failed tasks", data.dashboard.failed_tasks, "task failures"],
                ["Queue pending", data.dashboard.queue_pending, "pending / retrying"],
                ["Open DLQ", data.dashboard.dlq_open, "requires disposition"],
                ["Provider risk", data.dashboard.degraded_providers, "degraded / open / disabled"],
                ["Webhook backlog", data.dashboard.payment_events_pending, "billing received"],
                ["Provider cost · 24h", `$${data.dashboard.provider_cost_24h}`, "USD provider cost"],
              ].map(([label, value, detail]) => (
                <article className="metric-card" key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                  <small>{detail}</small>
                </article>
              ))}
            </section>

            <section className="panel" id="section-1">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">SAFE METADATA</p>
                  <h2>Failing runs</h2>
                </div>
                <span>{data.runs.length} visible</span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Run</th><th>Graph</th><th>Versions</th><th>Budget</th><th>Updated</th></tr></thead>
                  <tbody>
                    {data.runs.map((run) => (
                      <tr key={run.id}>
                        <td><strong>{shortId(run.id)}</strong><small>{shortId(run.organization_id)} / {shortId(run.project_id)}</small></td>
                        <td>{run.graph_key}<small>{run.status}</small></td>
                        <td>{run.graph_version}<small>agent {run.agent_config_version} · {shortId(run.code_git_sha)}</small></td>
                        <td>{run.budget_amount} {run.budget_currency}</td>
                        <td>{stamp(run.updated_at)}</td>
                      </tr>
                    ))}
                    {data.runs.length === 0 ? <tr><td colSpan={5} className="table-empty">No failing runs.</td></tr> : null}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="panel" id="section-2">
              <div className="panel-heading">
                <div><p className="eyebrow">QUEUE CONTROL</p><h2>Dead-letter queue</h2></div>
                <span>Payload hidden by contract</span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Message</th><th>Failure</th><th>Attempts</th><th>Last failure</th><th>Action</th></tr></thead>
                  <tbody>
                    {data.deadLetters.map((item) => (
                      <tr key={item.id}>
                        <td><strong>{shortId(item.id)}</strong><small>{item.message_kind} · {item.source_queue}</small></td>
                        <td>{item.error_category}<small>{item.error_code ?? "no code"} · {item.error_message}</small></td>
                        <td>{item.attempts}</td>
                        <td>{stamp(item.last_failed_at)}</td>
                        <td>
                          <div className="row-actions">
                            <button disabled={!permissions.has("queue.manage") || actionBusy !== null} onClick={() => onReplay(item)} type="button">Replay</button>
                            <button className="danger" disabled={!permissions.has("queue.manage") || actionBusy !== null || item.status !== "open"} onClick={() => onDiscard(item)} type="button">Discard</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {data.deadLetters.length === 0 ? <tr><td colSpan={5} className="table-empty">DLQ is empty.</td></tr> : null}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="panel" id="section-3">
              <div className="panel-heading">
                <div><p className="eyebrow">MODEL CONTROL PLANE</p><h2>Provider health</h2></div>
                <span>High-risk overrides require provider.manage</span>
              </div>
              <div className="provider-grid">
                {data.providers.map((provider, index) => (
                  <article className="provider-card" key={`${provider.provider}:${provider.model ?? "*"}:${provider.capability ?? "*"}:${index}`}>
                    <div className="provider-head">
                      <div><strong>{provider.provider}</strong><span>{provider.model ?? "provider-wide"}</span></div>
                      <span className={`health-pill health-${provider.state}`}>{provider.state}</span>
                    </div>
                    <div className="score-line"><span>Health score</span><strong>{provider.score}</strong></div>
                    <div className="score-track"><i style={{ width: `${provider.score}%` }} /></div>
                    <dl>
                      <div><dt>Capability</dt><dd>{provider.capability ?? "all"}</dd></div>
                      <div><dt>Observed</dt><dd>{stamp(provider.observed_at)}</dd></div>
                      <div><dt>Override</dt><dd>{provider.override_action ?? "none"}</dd></div>
                    </dl>
                    <div className="row-actions">
                      <button disabled={!permissions.has("provider.manage") || actionBusy !== null} onClick={() => onProviderAction(provider, "force_disabled")} type="button">Force disable</button>
                      <button disabled={!permissions.has("provider.manage") || actionBusy !== null} onClick={() => onProviderAction(provider, "clear_override")} type="button">Clear override</button>
                    </div>
                  </article>
                ))}
                {data.providers.length === 0 ? <div className="table-empty">No provider health snapshots.</div> : null}
              </div>
            </section>

            <section className="split-grid">
              <article className="panel" id="section-4">
                <div className="panel-heading"><div><p className="eyebrow">SERVER SIDE</p><h2>Feature flags</h2></div><span>{data.flags.length} active</span></div>
                <div className="flag-list">
                  {data.flags.map((flag) => (
                    <div className="flag-row" key={flag.id}>
                      <div><strong>{flag.flag_key}</strong><small>{flag.scope}{flag.target_id ? ` · ${shortId(flag.target_id)}` : ""}</small></div>
                      <code>{JSON.stringify(flag.value)}</code>
                      <span>{flag.expires_at ? `expires ${stamp(flag.expires_at)}` : "no expiry"}</span>
                    </div>
                  ))}
                  {data.flags.length === 0 ? <div className="table-empty">No active flags.</div> : null}
                </div>
              </article>

              <article className="panel locked-panel" id="section-5">
                <div className="lock-icon">↗</div>
                <p className="eyebrow">FAIL CLOSED</p>
                <h2>Registry promotion</h2>
                <p>
                  Production alias promotion remains disabled until a verifiable release-gate evidence adapter is composed.
                </p>
                <code>ADMIN_RELEASE_GATE_EVIDENCE_NOT_COMPOSED</code>
              </article>
            </section>

            <section className="footer-status" id="section-6">
              <span>Billing/customer revenue remains separate from provider cost facts.</span>
              <span id="section-7">Audit and break-glass records are append-only at the database layer.</span>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
