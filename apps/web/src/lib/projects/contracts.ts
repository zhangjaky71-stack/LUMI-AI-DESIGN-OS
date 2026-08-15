import { LumiApiError } from "@/lib/app-shell/api-client";
import type {
  CreateProjectInput,
  ProjectListFilters,
  StructuredBrief,
} from "./types";

const MAX_INTENT_LENGTH = 4_000;
const MAX_PROJECT_NAME_LENGTH = 120;
const MAX_BRIEF_FIELD_LENGTH = 4_000;
const MAX_PAGE_SIZE = 50;

export function normalizeProjectIntent(value: string): string {
  const normalized = value.trim().replace(/\s+/g, " ");
  if (!normalized) throw new Error("PROJECT_INTENT_REQUIRED");
  if (normalized.length > MAX_INTENT_LENGTH) {
    throw new Error("PROJECT_INTENT_TOO_LONG");
  }
  return normalized;
}

export function normalizeProjectName(value: string): string {
  const normalized = value.trim().replace(/\s+/g, " ");
  if (!normalized) throw new Error("PROJECT_NAME_REQUIRED");
  if (normalized.length > MAX_PROJECT_NAME_LENGTH) {
    throw new Error("PROJECT_NAME_TOO_LONG");
  }
  return normalized;
}

export function validateCreateProjectInput(
  input: CreateProjectInput,
): CreateProjectInput {
  const intent = normalizeProjectIntent(input.intent);
  const name = input.name ? normalizeProjectName(input.name) : null;
  if (!input.locale.trim()) throw new Error("PROJECT_LOCALE_REQUIRED");
  if (input.budget_microusd !== null && input.budget_microusd < 0n) {
    throw new Error("PROJECT_BUDGET_NEGATIVE");
  }
  return {
    ...input,
    intent,
    name,
    locale: input.locale.trim(),
    deliverables: Object.freeze(
      input.deliverables.map((value) => value.trim()).filter(Boolean),
    ),
  };
}

export function validateProjectListFilters(
  filters: ProjectListFilters,
): ProjectListFilters {
  if (!Number.isInteger(filters.limit) || filters.limit < 1 || filters.limit > MAX_PAGE_SIZE) {
    throw new Error("PROJECT_LIST_LIMIT_INVALID");
  }
  return {
    ...filters,
    query: filters.query.trim(),
  };
}

export function validateStructuredBrief(brief: StructuredBrief): StructuredBrief {
  const fields = [brief.objective, brief.audience, brief.notes];
  if (fields.some((value) => value.length > MAX_BRIEF_FIELD_LENGTH)) {
    throw new Error("PROJECT_BRIEF_FIELD_TOO_LONG");
  }
  if (!brief.locale.trim()) throw new Error("PROJECT_BRIEF_LOCALE_REQUIRED");
  return {
    ...brief,
    objective: brief.objective.trim(),
    audience: brief.audience.trim(),
    notes: brief.notes.trim(),
    locale: brief.locale.trim(),
    deliverables: Object.freeze(brief.deliverables.map((value) => value.trim()).filter(Boolean)),
    constraints: Object.freeze(brief.constraints.map((value) => value.trim()).filter(Boolean)),
    assumptions: Object.freeze(brief.assumptions.map((value) => value.trim()).filter(Boolean)),
  };
}

export function projectProblem(code: string, status = 409): LumiApiError {
  return new LumiApiError({
    type: `https://errors.lumi.dev/project/${code.toLowerCase().replaceAll("_", "-")}`,
    title: "Project operation failed",
    status,
    code,
    request_id: `projects-ui-${code.toLowerCase()}`,
  });
}

export function isVersionConflict(error: unknown): boolean {
  return error instanceof LumiApiError && error.problem.code === "VERSION_CONFLICT";
}

export function formatMicrousd(value: bigint | null): string | null {
  if (value === null) return null;
  const dollars = value / 1_000_000n;
  const remainder = value % 1_000_000n;
  return `${dollars}.${remainder.toString().padStart(6, "0")}`;
}
