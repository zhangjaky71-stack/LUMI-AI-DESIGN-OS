import Link from "next/link";

export default function HomePage() {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Design workspace</p>
          <h1>Build, review, and ship with LUMI.</h1>
          <p className="page-lead">
            Start from a project, move into the AI workspace, and keep every artifact,
            decision, and quality check connected.
          </p>
        </div>
        <Link className="primary-button" href="/projects">
          Open projects
        </Link>
      </section>

      <section className="shell-grid" aria-label="Workspace shortcuts">
        <Link className="feature-card" href="/projects">
          <span className="feature-index">01</span>
          <div>
            <h2>Projects</h2>
            <p>Organize briefs, artifacts, versions, and delivery work.</p>
          </div>
          <span className="feature-arrow" aria-hidden="true">↗</span>
        </Link>
        <Link className="feature-card" href="/workspace">
          <span className="feature-index">02</span>
          <div>
            <h2>AI Workspace</h2>
            <p>Continue into the agent and canvas workspace as the product surface lands.</p>
          </div>
          <span className="feature-arrow" aria-hidden="true">↗</span>
        </Link>
        <Link className="feature-card" href="/settings">
          <span className="feature-index">03</span>
          <div>
            <h2>Workspace settings</h2>
            <p>Review tenant context and the controls that govern your workspace.</p>
          </div>
          <span className="feature-arrow" aria-hidden="true">↗</span>
        </Link>
      </section>

      <section className="surface-card surface-card-muted">
        <div>
          <p className="eyebrow">Foundation ready</p>
          <h2>App Shell is the shared product frame.</h2>
        </div>
        <p>
          Project dashboards, AI workspace, canvas, layers, versions, and review flows
          attach to this shell in the next frontend nodes without duplicating auth,
          tenant, navigation, or API behavior.
        </p>
      </section>
    </div>
  );
}
