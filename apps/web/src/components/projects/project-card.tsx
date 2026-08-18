import Link from "next/link";

import type { ProjectSummary } from "@/lib/projects/types";

export function ProjectCard({ project }: { project: ProjectSummary }) {
  return (
    <Link className="project-card" href={`/projects/${encodeURIComponent(project.id)}`}>
      <div className="project-card-topline">
        <span className={`status-pill status-${normalizeStatus(project.status)}`}>
          {project.status}
        </span>
        <span className="project-open" aria-hidden="true">↗</span>
      </div>
      <div className="project-card-body">
        <h2>{project.name}</h2>
        <p>{project.description || "No project description yet."}</p>
      </div>
      <div className="project-card-meta">
        <span>Updated</span>
        <time dateTime={project.updatedAt ?? undefined}>
          {formatDate(project.updatedAt ?? project.createdAt)}
        </time>
      </div>
    </Link>
  );
}

function normalizeStatus(status: string): string {
  return status.toLowerCase().replace(/[^a-z0-9_-]/g, "-");
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}
