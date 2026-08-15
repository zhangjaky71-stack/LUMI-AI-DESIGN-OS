"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useShell } from "@/components/app-shell/shell-context";
import { projectUiError } from "@/lib/projects/client-utils";
import { isVersionConflict } from "@/lib/projects/contracts";
import { getProjectsGateway } from "@/lib/projects/projects-gateway";
import type {
  ProjectDetail as ProjectDetailModel,
  ProjectsBootstrap,
  StructuredBrief,
} from "@/lib/projects/types";
import styles from "./projects.module.css";

function lines(value: readonly string[]): string {
  return value.join("\n");
}

function fromLines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function ProjectDetail({
  projectId,
  bootstrap,
}: Readonly<{ projectId: string; bootstrap: ProjectsBootstrap }>) {
  const { activeOrganization, api, queryCache } = useShell();
  const gateway = useMemo(() => getProjectsGateway(api, bootstrap), [api, bootstrap]);
  const [detail, setDetail] = useState<ProjectDetailModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState<StructuredBrief | null>(null);
  const [deliverablesText, setDeliverablesText] = useState("");
  const [constraintsText, setConstraintsText] = useState("");
  const [assumptionsText, setAssumptionsText] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await queryCache.fetchQuery(
        ["project-detail", projectId],
        (signal) => gateway.getProject(activeOrganization.id, projectId, signal),
        10_000,
      );
      setDetail(result);
    } catch (loadError) {
      if (loadError instanceof Error && loadError.message === "QUERY_SCOPE_CHANGED") return;
      setError(projectUiError(loadError));
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }, [activeOrganization.id, gateway, projectId, queryCache]);

  useEffect(() => {
    void load();
  }, [load]);

  const beginEdit = () => {
    if (!detail) return;
    setDraft({ ...detail.brief });
    setDeliverablesText(lines(detail.brief.deliverables));
    setConstraintsText(lines(detail.brief.constraints));
    setAssumptionsText(lines(detail.brief.assumptions));
    setEditing(true);
    setNotice(null);
    setError(null);
  };

  const saveBrief = async () => {
    if (!detail || !draft) return;
    setSaving(true);
    setError(null);
    try {
      const result = await gateway.updateBrief(activeOrganization.id, {
        project_id: detail.summary.id,
        expected_project_version: detail.summary.version,
        expected_brief_version: detail.brief_version,
        brief: {
          ...draft,
          deliverables: fromLines(deliverablesText),
          constraints: fromLines(constraintsText),
          assumptions: fromLines(assumptionsText),
        },
      });
      const next: ProjectDetailModel = {
        ...detail,
        summary: result.project,
        brief_version: result.brief_version,
        brief: result.brief,
        brief_history: [
          ...detail.brief_history,
          {
            version: result.brief_version,
            created_at: result.project.last_activity_at,
            brief: result.brief,
          },
        ],
      };
      setDetail(next);
      queryCache.clear();
      setEditing(false);
      setDraft(null);
      setNotice(`Structured Brief 已保存为 v${result.brief_version}。历史版本仍可追溯。`);
    } catch (saveError) {
      setError(projectUiError(saveError));
      if (isVersionConflict(saveError)) {
        queryCache.clear();
        void load();
      }
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.projectDetailPage}>
        <div className={styles.detailSkeleton} aria-label="正在加载项目" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className={styles.projectDetailPage}>
        <Link className={styles.backLink} href="/app/projects">← 返回项目</Link>
        <div className={styles.errorState} role="alert">
          <p>{error ?? "当前组织中无法打开这个项目。"}</p>
          <button type="button" className={styles.secondaryButton} onClick={() => void load()}>重试</button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.projectDetailPage}>
      <Link className={styles.backLink} href="/app/projects">← 返回项目</Link>
      <header className={styles.detailHero}>
        <div>
          <div className={styles.detailStatusRow}>
            <span className={styles.statusPill} data-status={detail.summary.status}>{detail.summary.status}</span>
            <span>Project v{detail.summary.version}</span>
            <span>Brief v{detail.brief_version}</span>
          </div>
          <h1>{detail.summary.name}</h1>
          <p>
            {detail.summary.brand?.name ?? "未绑定 Brand"} · {detail.summary.artifact_count} Artifacts · {detail.summary.active_run_count} Active Runs
          </p>
        </div>
        <div className={styles.detailHeroActions}>
          <button type="button" className={styles.secondaryButton} onClick={beginEdit} disabled={editing}>编辑 Brief</button>
          <button type="button" className={styles.primaryButton} disabled title="NODE-54 接入 AI Workspace">
            进入 AI Workspace
          </button>
        </div>
      </header>

      {notice ? <p className={styles.notice} role="status">{notice}</p> : null}
      {error ? <p className={styles.formError} role="alert">{error}</p> : null}

      <div className={styles.detailGrid}>
        <section className={styles.briefPanel} aria-labelledby="structured-brief-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.eyebrow}>STRUCTURED BRIEF</p>
              <h2 id="structured-brief-title">设计 Brief</h2>
            </div>
            <span>v{detail.brief_version}</span>
          </div>

          {editing && draft ? (
            <div className={styles.briefEditor}>
              <label>
                <span>Objective</span>
                <textarea value={draft.objective} onChange={(event) => setDraft((current) => current ? { ...current, objective: event.target.value } : current)} />
              </label>
              <label>
                <span>Audience</span>
                <textarea value={draft.audience} onChange={(event) => setDraft((current) => current ? { ...current, audience: event.target.value } : current)} />
              </label>
              <div className={styles.fieldGrid}>
                <label>
                  <span>Deliverables · 每行一项</span>
                  <textarea value={deliverablesText} onChange={(event) => setDeliverablesText(event.target.value)} />
                </label>
                <label>
                  <span>Constraints · 每行一项</span>
                  <textarea value={constraintsText} onChange={(event) => setConstraintsText(event.target.value)} />
                </label>
              </div>
              <label>
                <span>Assumptions · 每行一项</span>
                <textarea value={assumptionsText} onChange={(event) => setAssumptionsText(event.target.value)} />
              </label>
              <label>
                <span>Notes</span>
                <textarea value={draft.notes} onChange={(event) => setDraft((current) => current ? { ...current, notes: event.target.value } : current)} />
              </label>
              <div className={styles.dialogFooter}>
                <button type="button" className={styles.secondaryButton} onClick={() => setEditing(false)} disabled={saving}>取消</button>
                <button type="button" className={styles.primaryButton} onClick={() => void saveBrief()} disabled={saving}>
                  {saving ? "保存中…" : "保存为新 BriefVersion"}
                </button>
              </div>
            </div>
          ) : (
            <dl className={styles.briefDefinition}>
              <div><dt>Objective</dt><dd>{detail.brief.objective || "—"}</dd></div>
              <div><dt>Audience</dt><dd>{detail.brief.audience || "—"}</dd></div>
              <div><dt>Deliverables</dt><dd>{detail.brief.deliverables.length ? detail.brief.deliverables.join(" · ") : "待确认"}</dd></div>
              <div><dt>Constraints</dt><dd>{detail.brief.constraints.length ? detail.brief.constraints.join(" · ") : "暂无"}</dd></div>
              <div><dt>Assumptions</dt><dd>{detail.brief.assumptions.length ? detail.brief.assumptions.join(" · ") : "暂无"}</dd></div>
              <div><dt>Locale</dt><dd>{detail.brief.locale}</dd></div>
            </dl>
          )}
        </section>

        <aside className={styles.detailAside}>
          <section className={styles.sidePanel} aria-labelledby="references-title">
            <div className={styles.sectionHeading}>
              <h2 id="references-title">参考素材</h2>
              <span>{detail.references.length}</span>
            </div>
            {detail.references.length === 0 ? (
              <p className={styles.mutedText}>还没有项目参考素材。后续可从 Project Dashboard 或 Workspace 继续添加。</p>
            ) : (
              <div className={styles.detailReferenceList}>
                {detail.references.map((reference) => (
                  <div key={reference.id} className={styles.detailReferenceRow}>
                    <div><strong>{reference.file_name}</strong><span>{reference.role}</span></div>
                    <span data-status={reference.scan_status}>
                      {reference.scan_status === "REJECTED" ? `不可用 · ${reference.failure_code ?? "REJECTED"}` : reference.scan_status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className={styles.sidePanel} aria-labelledby="brief-history-title">
            <div className={styles.sectionHeading}>
              <h2 id="brief-history-title">Brief 历史</h2>
              <span>{detail.brief_history.length}</span>
            </div>
            <ol className={styles.versionList}>
              {[...detail.brief_history].reverse().map((version) => (
                <li key={version.version}>
                  <strong>v{version.version}</strong>
                  <span>{new Date(version.created_at).toLocaleString("zh-CN")}</span>
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>
    </div>
  );
}
