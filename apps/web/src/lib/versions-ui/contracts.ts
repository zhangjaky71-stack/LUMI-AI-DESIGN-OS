import { LumiApiError } from "@/lib/app-shell/api-client";
import type {
  ForkVersionInput,
  RestoreVersionInput,
  SafeVersionProvenance,
  VersionSemanticChange,
  VersionTimelineItem,
} from "./types";

const BRANCH_NAME = /^[a-z0-9][a-z0-9-_]{1,38}[a-z0-9]$/;

export function versionsProblem(code: string, status = 409): LumiApiError {
  return new LumiApiError({
    type: `https://errors.lumi.dev/versions/${code.toLowerCase().replaceAll("_", "-")}`,
    title: code,
    status,
    code,
    request_id: `versions-${code.toLowerCase()}`,
  });
}

export function normalizeBranchName(value: string): string {
  return value.trim().toLowerCase().replaceAll(/\s+/g, "-");
}

export function validateForkInput(input: ForkVersionInput): ForkVersionInput {
  const name = normalizeBranchName(input.name);
  if (!BRANCH_NAME.test(name)) throw versionsProblem("BRANCH_NAME_INVALID", 400);
  return { ...input, name };
}

export function validateRestoreInput(input: RestoreVersionInput): RestoreVersionInput {
  if (!input.artifact_id || !input.branch_id || !input.source_version_id) {
    throw versionsProblem("RESTORE_INPUT_INVALID", 400);
  }
  return input;
}

export function renderSemanticSummary(changes: readonly VersionSemanticChange[]): string {
  if (!changes.length) return "No semantic property changes.";
  return changes.map((change) => change.label).join(" · ");
}

export function exactCompareChanges(
  from: VersionTimelineItem,
  to: VersionTimelineItem,
): readonly VersionSemanticChange[] {
  if (from.version.id === to.version.id) return [];
  return to.semantic_changes;
}

export function safeProvenance(
  item: VersionTimelineItem,
  source: {
    readonly model?: string;
    readonly provider?: string;
    readonly agent_run_id?: string;
    readonly task_id?: string;
    readonly generation_id?: string;
    readonly recipe_version?: string;
    readonly skill_versions?: Readonly<Record<string, string>>;
    readonly input_asset_ids?: readonly string[];
    readonly input_artifact_version_ids?: readonly string[];
    readonly brand_rule_set_version?: string;
    readonly constraint_snapshot_hash: string;
    readonly prompt_hash?: string;
    readonly prompt_template_version?: string;
    readonly code_git_sha: string;
    readonly compiler?: SafeVersionProvenance["compiler"];
  },
): SafeVersionProvenance {
  return {
    artifact_version_id: item.version.id,
    created_by_type: item.version.created_by_type,
    created_by_id: item.version.created_by_id,
    model: source.model ?? null,
    provider: source.provider ?? null,
    agent_run_id: source.agent_run_id ?? null,
    task_id: source.task_id ?? null,
    generation_id: source.generation_id ?? null,
    recipe_version: source.recipe_version ?? null,
    skill_versions: source.skill_versions ?? {},
    input_asset_ids: source.input_asset_ids ?? [],
    input_artifact_version_ids: source.input_artifact_version_ids ?? [],
    brand_rule_set_version: source.brand_rule_set_version ?? item.version.brand_rule_set_version ?? null,
    constraint_snapshot_hash: source.constraint_snapshot_hash,
    prompt_hash: source.prompt_hash ?? null,
    prompt_template_version: source.prompt_template_version ?? null,
    code_git_sha: source.code_git_sha,
    compiler: source.compiler ?? null,
    quality_checks: item.quality.checks,
  };
}
