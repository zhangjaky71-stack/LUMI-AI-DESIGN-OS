import Link from "next/link";

export default function ProjectsShellPage() {
  return (
    <div className="page-stack">
      <section className="page-heading compact">
        <div>
          <p className="eyebrow">Projects</p>
          <h1>Project workspace</h1>
          <p className="page-lead">
            The App Shell owns routing and tenant context here. Project discovery,
            creation, filters, and brief flows are implemented in NODE-53.
          </p>
        </div>
      </section>
      <section className="surface-card empty-surface" aria-labelledby="projects-next-title">
        <span className="empty-kicker">NODE-53 handoff</span>
        <h2 id="projects-next-title">Projects UI attaches here.</h2>
        <p>No mock project records are rendered by the shell.</p>
        <Link className="secondary-button" href="/">
          Back home
        </Link>
      </section>
    </div>
  );
}
