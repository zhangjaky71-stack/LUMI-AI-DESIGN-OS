import Link from "next/link";

import { ProjectCard } from "@/components/projects/project-card";
import { listProjects } from "@/lib/projects/api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  q?: string | string[];
  status?: string | string[];
}>;

export default async function ProjectsDashboardPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const params = await searchParams;
  const query = single(params.q).trim().toLowerCase();
  const status = single(params.status).trim().toUpperCase();
  const projects = await listProjects();
  const visible = projects
    .filter((project) => {
      const matchesQuery =
        !query ||
        project.name.toLowerCase().includes(query) ||
        (project.description ?? "").toLowerCase().includes(query);
      const matchesStatus = !status || project.status.toUpperCase() === status;
      return matchesQuery && matchesStatus;
    })
    .toSorted((left, right) => timestamp(right.updatedAt) - timestamp(left.updatedAt));

  const statuses = [...new Set(projects.map((project) => project.status.toUpperCase()))]
    .filter(Boolean)
    .toSorted();

  return (
    <div className="page-stack projects-dashboard">
      <section className="page-heading project-heading">
        <div>
          <p className="eyebrow">Projects</p>
          <h1>Your creative work, in one place.</h1>
          <p className="page-lead">
            Every brief, artifact, version, agent run, and review belongs to a durable project.
          </p>
        </div>
        <Link className="primary-button" href="/projects/new">
          New project
        </Link>
      </section>

      <form className="project-toolbar" method="get" role="search">
        <label className="search-field">
          <span className="sr-only">Search projects</span>
          <input
            type="search"
            name="q"
            defaultValue={single(params.q)}
            placeholder="Search projects"
          />
        </label>
        <label className="filter-field">
          <span className="sr-only">Filter by status</span>
          <select name="status" defaultValue={status}>
            <option value="">All statuses</option>
            {statuses.map((value) => (
              <option value={value} key={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <button className="secondary-button" type="submit">
          Apply
        </button>
        {query || status ? (
          <Link className="text-link" href="/projects/dashboard">
            Clear
          </Link>
        ) : null}
      </form>

      <div className="project-result-row">
        <span>
          {visible.length} {visible.length === 1 ? "project" : "projects"}
        </span>
        {projects.length > visible.length ? (
          <span>{projects.length - visible.length} filtered out</span>
        ) : null}
      </div>

      {visible.length > 0 ? (
        <section className="project-grid" aria-label="Projects">
          {visible.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </section>
      ) : (
        <section className="surface-card empty-surface project-empty">
          <span className="empty-kicker">No matching projects</span>
          <h2>{projects.length ? "Adjust your filters." : "Create your first project."}</h2>
          <p>
            {projects.length
              ? "Try a different search term or status."
              : "Start with a brief, then let LUMI connect generation, review, and delivery work to it."}
          </p>
          {projects.length ? (
            <Link className="secondary-button" href="/projects/dashboard">
              Clear filters
            </Link>
          ) : (
            <Link className="primary-button" href="/projects/new">
              New project
            </Link>
          )}
        </section>
      )}
    </div>
  );
}

function single(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function timestamp(value?: string | null): number {
  if (!value) return 0;
  const date = new Date(value).getTime();
  return Number.isNaN(date) ? 0 : date;
}
