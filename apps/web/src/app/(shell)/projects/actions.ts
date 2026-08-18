"use server";

import { redirect } from "next/navigation";

import { ApiError } from "@/lib/api/problem";
import { createProject } from "@/lib/projects/api";
import type { CreateProjectInput } from "@/lib/projects/types";

export type CreateProjectState = {
  status: "idle" | "error";
  message?: string;
  fieldErrors?: Partial<Record<keyof CreateProjectInput | "operationId", string>>;
};

export const INITIAL_CREATE_PROJECT_STATE: CreateProjectState = {
  status: "idle",
};

export async function createProjectAction(
  _previous: CreateProjectState,
  formData: FormData,
): Promise<CreateProjectState> {
  const input: CreateProjectInput = {
    name: text(formData, "name"),
    description: text(formData, "description"),
    objective: text(formData, "objective"),
    audience: text(formData, "audience"),
    deliverables: lines(formData, "deliverables"),
    constraints: lines(formData, "constraints"),
  };
  const operationId = text(formData, "operationId");
  const fieldErrors = validate(input, operationId);
  if (Object.keys(fieldErrors).length > 0) {
    return {
      status: "error",
      message: "Review the highlighted project details.",
      fieldErrors,
    };
  }

  try {
    const project = await createProject(input, operationId);
    redirect(`/projects/${encodeURIComponent(project.id)}`);
  } catch (error) {
    if (isRedirect(error)) throw error;
    if (error instanceof ApiError) {
      return {
        status: "error",
        message:
          error.status === 409
            ? "A project with this operation is already being created. Retry from Projects."
            : error.message,
      };
    }
    return {
      status: "error",
      message: "Project creation could not be completed. Try again.",
    };
  }
}

function validate(
  input: CreateProjectInput,
  operationId: string,
): CreateProjectState["fieldErrors"] {
  const errors: NonNullable<CreateProjectState["fieldErrors"]> = {};
  if (input.name.trim().length < 2 || input.name.length > 120) {
    errors.name = "Use a project name between 2 and 120 characters.";
  }
  if ((input.description?.length ?? 0) > 1_000) {
    errors.description = "Keep the description under 1,000 characters.";
  }
  if ((input.objective?.length ?? 0) > 2_000) {
    errors.objective = "Keep the objective under 2,000 characters.";
  }
  if ((input.audience?.length ?? 0) > 1_000) {
    errors.audience = "Keep the audience under 1,000 characters.";
  }
  if (input.deliverables.length > 20) {
    errors.deliverables = "Use at most 20 deliverables.";
  }
  if (input.constraints.length > 20) {
    errors.constraints = "Use at most 20 constraints.";
  }
  if (!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(operationId)) {
    errors.operationId = "Refresh the form before submitting.";
  }
  return errors;
}

function text(formData: FormData, key: string): string {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function lines(formData: FormData, key: string): readonly string[] {
  return text(formData, key)
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean);
}

function isRedirect(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "digest" in error &&
    typeof (error as { digest?: unknown }).digest === "string" &&
    (error as { digest: string }).digest.startsWith("NEXT_REDIRECT")
  );
}
