import Link from "next/link";

import { getProject } from "@/lib/projects/api";

export const dynamic = "force-dynamic";

type Params = Promise<{ projectId: string }>;

export default async function ProjectDetailPage({ params }: { params: Params }) {
  const { projectId } = await params;
  const project = await getProject(projectId);
  const brief = project.brief;

  return (
    <div className="page-stack project-detail">
      <section className="page-heading project-heading">
        <div>
          <div className="project-breadcrumbs" aria-label="Breadcrumb">
            <Link href="/projects/dashboard">Projects</Link>
            <span aria-hidden="true">/</span>
            <span aria-current="page">{project.name}</span>
          </div>
          <div className="project-title-row">
            <span className={`status-pill status-${normalizeStatus(project.status)}`}>
              {project.status}
            </span>
            <h1>{project.name}</h1>
          </div>
          <p className="page-lead">
            {project.description || "This project does not have a description yet."}
          </p>
        </div>
        <Link
          className="primary-button"
          href={`/workspace?project=${encodeURIComponent(project.id)}`}
        >
          Open AI Workspace
        </Link>
      </section>

      <section className="project-detail-grid">
        <article className="surface-card project-brief-card">
          <div>
            <p className="eyebrow">Creative brief</p>
            <h2>Objective</h2>
          </div>
          <p>{brief?.objective || "No objective has been recorded yet."}</p>
        </article>

        <article className="surface-card project-brief-card">
          <div>
            <p className="eyebrow">Audience</p>
            <h2>Who this is for</h2>
          </div>
          <p>{brief?.audience || "No audience definition has been recorded yet."}</p>
        </article>
      </section>

      <section className="project-list-panels">
        <ListPanel
          title="Deliverables"
          eyebrow="Expected outputs"
          values={brief?.deliverables ?? []}
          empty="No deliverables have been recorded yet."
        />
        <ListPanel
          title="Constraints"
          eyebrow="Hard requirements"
          values={brief?.constraints ?? []}
          empty="No explicit constraints have been recorded yet."
        />
      </section>

      <section className="surface-card surface-card-muted project-next-card">
        <div>
          <p className="eyebrow">Next step</p>
          <h2>Continue from the project context.</h2>
        </div>
        <p>
          The AI Workspace receives the durable project identifier through the route handoff.
          Agent chat, canvas, task streaming, and approval state are implemented in NODE-54 and
          later frontend nodes rather than fabricated here.
        </p>
      </section>
    </div>
  );
}

function ListPanel({
  title,
  eyebrow,
  values,
  empty,
}: {
  title: string;
  eyebrow: string;
  values: readonly string[];
  empty: string;
}) {
  return (
    <article className="list-panel">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      {values.length ? (
        <ul>
          {values.map((value, index) => (
            <li key={`${index}-${value}`}>{value}</li>
          ))}
        </ul>
      ) : (
        <p className="list-panel-empty">{empty}</p>
      )}
    </article>
  );
}

function normalizeStatus(status: string): string {
  return status.toLowerCase().replace(/[^a-z0-9_-]/g, "-");
}
