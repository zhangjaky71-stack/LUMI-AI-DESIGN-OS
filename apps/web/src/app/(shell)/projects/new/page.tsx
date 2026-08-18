import Link from "next/link";

import { NewProjectForm } from "@/components/projects/new-project-form";

export default function NewProjectPage() {
  const operationId = crypto.randomUUID();
  return (
    <div className="page-stack">
      <section className="page-heading compact project-heading">
        <div>
          <p className="eyebrow">New project</p>
          <h1>Start with a clear brief.</h1>
          <p className="page-lead">
            Create the durable project context first. Agents, artifacts, versions, and
            approvals attach to this project after creation.
          </p>
        </div>
        <Link className="text-link" href="/projects">
          Back to projects
        </Link>
      </section>
      <NewProjectForm operationId={operationId} />
    </div>
  );
}
