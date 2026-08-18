"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import {
  INITIAL_CREATE_PROJECT_STATE,
  createProjectAction,
} from "@/app/(shell)/projects/actions";

export function NewProjectForm({ operationId }: { operationId: string }) {
  const [state, action] = useActionState(
    createProjectAction,
    INITIAL_CREATE_PROJECT_STATE,
  );

  return (
    <form action={action} className="project-form">
      <input type="hidden" name="operationId" value={operationId} />

      {state.status === "error" && state.message ? (
        <div className="form-banner error" role="alert">
          {state.message}
        </div>
      ) : null}

      <section className="form-section" aria-labelledby="project-basics-heading">
        <div className="form-section-copy">
          <span className="form-step">01</span>
          <div>
            <h2 id="project-basics-heading">Project basics</h2>
            <p>Name the work clearly so every artifact and agent run has a stable home.</p>
          </div>
        </div>
        <div className="form-fields">
          <Field
            label="Project name"
            name="name"
            required
            maxLength={120}
            placeholder="Summer product launch"
            error={state.fieldErrors?.name}
          />
          <TextAreaField
            label="Description"
            name="description"
            maxLength={1000}
            rows={4}
            placeholder="A short description of what this project covers."
            error={state.fieldErrors?.description}
          />
        </div>
      </section>

      <section className="form-section" aria-labelledby="project-brief-heading">
        <div className="form-section-copy">
          <span className="form-step">02</span>
          <div>
            <h2 id="project-brief-heading">Creative brief</h2>
            <p>Give the system enough intent to plan work without inventing requirements.</p>
          </div>
        </div>
        <div className="form-fields">
          <TextAreaField
            label="Objective"
            name="objective"
            maxLength={2000}
            rows={5}
            placeholder="What outcome should the creative work achieve?"
            error={state.fieldErrors?.objective}
          />
          <TextAreaField
            label="Audience"
            name="audience"
            maxLength={1000}
            rows={4}
            placeholder="Who is the work for, and what matters to them?"
            error={state.fieldErrors?.audience}
          />
        </div>
      </section>

      <section className="form-section" aria-labelledby="project-output-heading">
        <div className="form-section-copy">
          <span className="form-step">03</span>
          <div>
            <h2 id="project-output-heading">Outputs & constraints</h2>
            <p>One item per line. Keep hard requirements explicit and auditable.</p>
          </div>
        </div>
        <div className="form-fields two-column">
          <TextAreaField
            label="Deliverables"
            name="deliverables"
            rows={6}
            placeholder={"Hero campaign visual\nSocial adaptations\nLaunch presentation"}
            hint="Up to 20 items."
            error={state.fieldErrors?.deliverables}
          />
          <TextAreaField
            label="Constraints"
            name="constraints"
            rows={6}
            placeholder={"Keep product identity unchanged\nUse approved brand type\nLaunch before campaign date"}
            hint="Up to 20 items."
            error={state.fieldErrors?.constraints}
          />
        </div>
      </section>

      <div className="form-actions">
        <a className="secondary-button" href="/projects">
          Cancel
        </a>
        <SubmitButton />
      </div>
    </form>
  );
}

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button className="primary-button" type="submit" disabled={pending}>
      {pending ? "Creating…" : "Create project"}
    </button>
  );
}

function Field({
  label,
  name,
  error,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  name: string;
  error?: string;
}) {
  const errorId = `${name}-error`;
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <input
        {...props}
        name={name}
        className="field-control"
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : undefined}
      />
      {error ? (
        <span className="field-error" id={errorId}>
          {error}
        </span>
      ) : null}
    </label>
  );
}

function TextAreaField({
  label,
  name,
  error,
  hint,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label: string;
  name: string;
  error?: string;
  hint?: string;
}) {
  const errorId = `${name}-error`;
  const hintId = `${name}-hint`;
  const describedBy = [error ? errorId : null, hint ? hintId : null]
    .filter(Boolean)
    .join(" ") || undefined;
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <textarea
        {...props}
        name={name}
        className="field-control field-textarea"
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
      />
      {hint ? (
        <span className="field-hint" id={hintId}>
          {hint}
        </span>
      ) : null}
      {error ? (
        <span className="field-error" id={errorId}>
          {error}
        </span>
      ) : null}
    </label>
  );
}
