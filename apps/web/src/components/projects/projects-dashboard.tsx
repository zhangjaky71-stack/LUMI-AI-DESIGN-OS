"use client";

import Link from "next/link";
import {
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useShell } from "@/components/app-shell/shell-context";
import {
  mergeProject,
  projectListQueryKey,
  projectUiError,
} from "@/lib/projects/client-utils";
import { isVersionConflict } from "@/lib/projects/contracts";
import { getProjectsGateway } from "@/lib/projects/projects-gateway";
import type {
  ProjectListFilters,
  ProjectStatus,
  ProjectSummary,
  ProjectsBootstrap,
  ProjectsViewMode,
} from "@/lib/projects/types";
import { NewProjectDialog } from "./new-project-dialog";
import styles from "./projects.module.css";

const STATUS_LABEL: Readonly<Record<ProjectStatus, string>> = {
  DRAFT: "草稿",
  ACTIVE: "进行中",
  PAUSED: "已暂停",
  ARCHIVED: "已归档",
};

function formatActivity(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function matchesFilters(project: ProjectSummary, filters: ProjectListFilters): boolean {
  if (filters.status !== "ALL" && project.status !== filters.status) return false;
  if (filters.workspace_id && project.workspace_id !== filters.workspace_id) return false;
  if (filters.brand_id && project.brand?.id !== filters.brand_id) return false;
  if (filters.query && !project.name.toLocaleLowerCase("zh-CN").includes(filters.query.toLocaleLowerCase("zh-CN"))) {
    return false;
  }
  return true;
}

export function ProjectsDashboard({ bootstrap }: Readonly<{ bootstrap: ProjectsBootstrap }>) {
  const { activeOrganization, api, queryCache } = useShell();
  const gateway = useMemo(() => getProjectsGateway(api, bootstrap), [api, bootstrap]);
  const [filters, setFilters] = useState<ProjectListFilters>({
    query: "",
    status: "ALL",
    workspace_id: null,
    brand_id: null,
    sort: "recent",
    cursor: null,
    limit: bootstrap.page_size,
  });
  const deferredQuery = useDeferredValue(filters.query);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ProjectsViewMode>("grid");
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<ProjectSummary | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [archiveTarget, setArchiveTarget] = useState<ProjectSummary | null>(null);
  const [mutationBusy, setMutationBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const effectiveFilters = useMemo<ProjectListFilters>(
    () => ({ ...filters, query: deferredQuery, cursor: null }),
    [deferredQuery, filters],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await queryCache.fetchQuery(
        projectListQueryKey(effectiveFilters),
        (signal) =>
          gateway.listProjects(
            activeOrganization.id,
            effectiveFilters,
            signal,
          ),
        15_000,
      );
      setProjects([...page.items]);
      setNextCursor(page.next_cursor);
      setHasMore(page.has_more);
    } catch (loadError) {
      if (loadError instanceof Error && loadError.message === "QUERY_SCOPE_CHANGED") return;
      setProjects([]);
      setError(projectUiError(loadError));
    } finally {
      setLoading(false);
    }
  }, [activeOrganization.id, effectiveFilters, gateway, queryCache]);

  useEffect(() => {
    void load();
  }, [load]);

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    setError(null);
    const moreFilters = { ...effectiveFilters, cursor: nextCursor };
    try {
      const page = await queryCache.fetchQuery(
        projectListQueryKey(moreFilters),
        (signal) => gateway.listProjects(activeOrganization.id, moreFilters, signal),
        15_000,
      );
      setProjects((current) => {
        const byId = new Map(current.map((project) => [project.id, project]));
        for (const project of page.items) byId.set(project.id, project);
        return [...byId.values()];
      });
      setNextCursor(page.next_cursor);
      setHasMore(page.has_more);
    } catch (loadError) {
      setError(projectUiError(loadError));
    } finally {
      setLoadingMore(false);
    }
  };

  const handleCreated = (project: ProjectSummary) => {
    queryCache.clear();
    if (matchesFilters(project, effectiveFilters)) {
      setProjects((current) => mergeProject(current, project));
    }
    setNotice(`“${project.name}”已创建。`);
  };

  const saveRename = async () => {
    if (!renameTarget || !renameValue.trim()) return;
    const target = renameTarget;
    const previous = projects;
    const optimistic = { ...target, name: renameValue.trim() };
    setProjects((current) => mergeProject(current, optimistic));
    setMutationBusy(true);
    setNotice(null);
    try {
      const result = await gateway.renameProject(activeOrganization.id, {
        project_id: target.id,
        name: renameValue,
        expected_version: target.version,
      });
      setProjects((current) => mergeProject(current, result.project));
      queryCache.clear();
      setRenameTarget(null);
      setNotice("项目名称已更新。");
    } catch (renameError) {
      setProjects(previous);
      setError(projectUiError(renameError));
      if (isVersionConflict(renameError)) {
        queryCache.clear();
        void load();
      }
    } finally {
      setMutationBusy(false);
    }
  };

  const archive = async () => {
    if (!archiveTarget) return;
    setMutationBusy(true);
    setError(null);
    try {
      const result = await gateway.archiveProject(
        activeOrganization.id,
        archiveTarget.id,
        archiveTarget.version,
      );
      queryCache.clear();
      setProjects((current) =>
        effectiveFilters.status !== "ALL" && effectiveFilters.status !== "ARCHIVED"
          ? current.filter((project) => project.id !== archiveTarget.id)
          : mergeProject(current, result.project),
      );
      setArchiveTarget(null);
      setNotice("项目已归档。历史 Agent Run 不会自动删除。 ");
    } catch (archiveError) {
      setError(projectUiError(archiveError));
    } finally {
      setMutationBusy(false);
    }
  };

  const restore = async (project: ProjectSummary) => {
    setMutationBusy(true);
    setError(null);
    try {
      const result = await gateway.restoreProject(
        activeOrganization.id,
        project.id,
        project.version,
      );
      queryCache.clear();
      setProjects((current) =>
        effectiveFilters.status === "ARCHIVED"
          ? current.filter((item) => item.id !== project.id)
          : mergeProject(current, result.project),
      );
      setNotice("项目已恢复。历史 Agent Run 不会自动重启。");
    } catch (restoreError) {
      setError(projectUiError(restoreError));
    } finally {
      setMutationBusy(false);
    }
  };

  const recent = projects.filter((project) => project.status !== "ARCHIVED").slice(0, 3);

  return (
    <div className={styles.projectsPage}>
      <section className={styles.projectsHero}>
        <div>
          <p className={styles.eyebrow}>PROJECTS</p>
          <h1>项目</h1>
          <p>从一句话开始，管理 Brief、参考素材、设计版本与 Agent 工作。</p>
        </div>
        <button
          type="button"
          className={styles.primaryButton}
          onClick={() => setNewProjectOpen(true)}
        >
          新建项目
        </button>
      </section>

      {recent.length > 0 && !filters.query && filters.status === "ALL" ? (
        <section aria-labelledby="recent-projects-title" className={styles.recentSection}>
          <div className={styles.sectionHeading}>
            <h2 id="recent-projects-title">最近项目</h2>
            <span>{activeOrganization.name}</span>
          </div>
          <div className={styles.recentGrid}>
            {recent.map((project) => (
              <Link key={project.id} href={`/app/projects/${project.id}`} className={styles.recentCard}>
                <span className={styles.previewMini}>{project.preview_label ?? "Project"}</span>
                <strong>{project.name}</strong>
                <span>{formatActivity(project.last_activity_at)}</span>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <section className={styles.projectPanel} aria-labelledby="all-projects-title">
        <div className={styles.panelHeader}>
          <div>
            <h2 id="all-projects-title">全部项目</h2>
            <p>列表数据始终以当前 Organization 为 scope。</p>
          </div>
          <div className={styles.viewToggle} aria-label="项目视图">
            <button type="button" data-active={viewMode === "grid"} onClick={() => setViewMode("grid")}>卡片</button>
            <button type="button" data-active={viewMode === "list"} onClick={() => setViewMode("list")}>列表</button>
          </div>
        </div>

        <div className={styles.filters}>
          <label className={styles.searchField}>
            <span className={styles.visuallyHidden}>搜索项目</span>
            <input
              type="search"
              value={filters.query}
              onChange={(event) => setFilters((current) => ({ ...current, query: event.target.value }))}
              placeholder="搜索项目…"
            />
          </label>
          <select
            aria-label="项目状态"
            value={filters.status}
            onChange={(event) =>
              setFilters((current) => ({ ...current, status: event.target.value as ProjectStatus | "ALL" }))
            }
          >
            <option value="ALL">全部状态</option>
            <option value="ACTIVE">进行中</option>
            <option value="DRAFT">草稿</option>
            <option value="PAUSED">已暂停</option>
            <option value="ARCHIVED">已归档</option>
          </select>
          {bootstrap.workspace_options.length > 0 ? (
            <select
              aria-label="工作区"
              value={filters.workspace_id ?? ""}
              onChange={(event) =>
                setFilters((current) => ({ ...current, workspace_id: event.target.value || null }))
              }
            >
              <option value="">全部工作区</option>
              {bootstrap.workspace_options.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
              ))}
            </select>
          ) : null}
          {bootstrap.brand_options.length > 0 ? (
            <select
              aria-label="品牌"
              value={filters.brand_id ?? ""}
              onChange={(event) =>
                setFilters((current) => ({ ...current, brand_id: event.target.value || null }))
              }
            >
              <option value="">全部品牌</option>
              {bootstrap.brand_options.map((brand) => (
                <option key={brand.id} value={brand.id}>{brand.name}</option>
              ))}
            </select>
          ) : null}
          <select
            aria-label="排序"
            value={filters.sort}
            onChange={(event) =>
              setFilters((current) => ({ ...current, sort: event.target.value as ProjectListFilters["sort"] }))
            }
          >
            <option value="recent">最近活动</option>
            <option value="created">最近创建</option>
            <option value="name">名称</option>
          </select>
        </div>

        {notice ? <p className={styles.notice} role="status">{notice}</p> : null}
        {error ? (
          <div className={styles.errorState} role="alert">
            <p>{error}</p>
            <button type="button" className={styles.secondaryButton} onClick={() => void load()}>重试</button>
          </div>
        ) : null}

        {loading ? (
          <div className={styles.projectSkeletonGrid} aria-label="正在加载项目">
            {Array.from({ length: 4 }, (_, index) => <span key={index} />)}
          </div>
        ) : projects.length === 0 ? (
          <div className={styles.emptyProjects}>
            <div className={styles.emptyGlyph} aria-hidden="true">✦</div>
            <h3>{filters.query || filters.status !== "ALL" ? "没有匹配项目" : "从第一个设计任务开始"}</h3>
            <p>
              {filters.query || filters.status !== "ALL"
                ? "调整搜索或筛选条件。"
                : "你可以只说一句“帮我做一套新品发布视觉”，其余上下文稍后再补。"}
            </p>
            <button type="button" className={styles.primaryButton} onClick={() => setNewProjectOpen(true)}>
              新建项目
            </button>
          </div>
        ) : (
          <div className={viewMode === "grid" ? styles.projectGrid : styles.projectList} data-view={viewMode}>
            {projects.map((project) => (
              <article key={project.id} className={styles.projectCard}>
                <Link href={`/app/projects/${project.id}`} className={styles.projectPreview} aria-label={`打开项目 ${project.name}`}>
                  <span className={styles.previewLabel}>{project.preview_label ?? "LUMI Project"}</span>
                  <span className={styles.previewMetric}>{project.artifact_count} artifacts</span>
                </Link>
                <div className={styles.projectCardBody}>
                  <div className={styles.projectTitleRow}>
                    <div>
                      <span className={styles.statusPill} data-status={project.status}>{STATUS_LABEL[project.status]}</span>
                      <h3><Link href={`/app/projects/${project.id}`}>{project.name}</Link></h3>
                    </div>
                    <span className={styles.activityTime}>{formatActivity(project.last_activity_at)}</span>
                  </div>
                  <div className={styles.projectMeta}>
                    <span>{project.brand?.name ?? "未绑定 Brand"}</span>
                    <span>{project.active_run_count > 0 ? `${project.active_run_count} Agent running` : "Agent idle"}</span>
                  </div>
                  <div className={styles.projectActions}>
                    <button
                      type="button"
                      className={styles.textButton}
                      onClick={() => {
                        setRenameTarget(project);
                        setRenameValue(project.name);
                        setError(null);
                      }}
                    >
                      重命名
                    </button>
                    {project.status === "ARCHIVED" ? (
                      <button type="button" className={styles.textButton} disabled={mutationBusy} onClick={() => void restore(project)}>
                        恢复
                      </button>
                    ) : (
                      <button type="button" className={styles.textButtonDanger} onClick={() => setArchiveTarget(project)}>
                        归档
                      </button>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}

        {hasMore ? (
          <div className={styles.loadMoreRow}>
            <button type="button" className={styles.secondaryButton} onClick={() => void loadMore()} disabled={loadingMore}>
              {loadingMore ? "加载中…" : "加载更多"}
            </button>
          </div>
        ) : null}
      </section>

      <NewProjectDialog
        open={newProjectOpen}
        organizationId={activeOrganization.id}
        bootstrap={bootstrap}
        gateway={gateway}
        onClose={() => setNewProjectOpen(false)}
        onCreated={handleCreated}
      />

      {renameTarget ? (
        <div className={styles.modalBackdrop}>
          <section className={styles.smallDialog} role="dialog" aria-modal="true" aria-labelledby="rename-project-title">
            <h2 id="rename-project-title">重命名项目</h2>
            <label className={styles.fieldLabel} htmlFor="rename-project-input">项目名称</label>
            <input
              id="rename-project-input"
              autoFocus
              className={styles.textInput}
              value={renameValue}
              onChange={(event) => setRenameValue(event.target.value)}
              maxLength={120}
            />
            <div className={styles.dialogFooter}>
              <button type="button" className={styles.secondaryButton} onClick={() => setRenameTarget(null)} disabled={mutationBusy}>取消</button>
              <button type="button" className={styles.primaryButton} onClick={() => void saveRename()} disabled={mutationBusy || !renameValue.trim()}>
                {mutationBusy ? "保存中…" : "保存"}
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {archiveTarget ? (
        <div className={styles.modalBackdrop}>
          <section className={styles.smallDialog} role="alertdialog" aria-modal="true" aria-labelledby="archive-project-title">
            <p className={styles.eyebrow}>ARCHIVE</p>
            <h2 id="archive-project-title">归档“{archiveTarget.name}”？</h2>
            <p>归档不会永久删除素材、Artifact 或历史 Agent Run，也不会自动取消数据保留策略。</p>
            <div className={styles.dialogFooter}>
              <button type="button" className={styles.secondaryButton} onClick={() => setArchiveTarget(null)} disabled={mutationBusy}>取消</button>
              <button type="button" className={styles.dangerButton} onClick={() => void archive()} disabled={mutationBusy}>
                {mutationBusy ? "归档中…" : "确认归档"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
