export default function WorkspaceShellPage() {
  return (
    <div className="page-stack">
      <section className="page-heading compact">
        <div>
          <p className="eyebrow">AI Workspace</p>
          <h1>Agent + canvas workspace</h1>
          <p className="page-lead">
            This route is reserved for the product workspace. Streaming agent state,
            canvas composition, approvals, and editing arrive in the dedicated frontend nodes.
          </p>
        </div>
      </section>
      <section className="surface-card empty-surface">
        <span className="empty-kicker">Frontend handoff</span>
        <h2>Workspace surface reserved.</h2>
        <p>The App Shell intentionally does not invent mock agent or canvas state.</p>
      </section>
    </div>
  );
}
