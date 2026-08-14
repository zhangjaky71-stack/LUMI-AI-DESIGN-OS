import { canonicalSha256 } from "../../design-ir/src/index";
import type { CriticSubject, QualityResult } from "../../quality-engine/src/index";
import { compareQuality } from "./comparator";
import { addUsd, canAfford, remainingUsd } from "./money";
import { buildRepairPlan } from "./planner";
import type { AutoRepairPorts, AutoRepairRunOptions, BudgetReservation } from "./ports";
import { executeStructuralRepair } from "./structural";
import type {
  CandidateMaterialization,
  PersistedRepairCandidate,
  RepairAttemptRecord,
  RepairLoopResult,
  RepairPlanItem,
  RepairSource,
} from "./types";

export class AutoRepairError extends Error {}
export class AutoRepairStaleSourceError extends AutoRepairError {}

function candidateSubject(source: RepairSource, candidate: PersistedRepairCandidate): CriticSubject {
  return {
    organization_id: source.subject.organization_id,
    project_id: source.subject.project_id,
    artifact_id: source.subject.artifact_id,
    artifact_version_id: candidate.artifact_version_id,
    design_document_version_id: candidate.design_document_version_id,
    design_document: candidate.design_document,
    rendered_asset_ref: candidate.rendered_asset_ref,
    ...(candidate.width !== undefined ? { width: candidate.width } : {}),
    ...(candidate.height !== undefined ? { height: candidate.height } : {}),
    ...(source.subject.expected_text ? { expected_text: source.subject.expected_text } : {}),
    ...(source.subject.metadata ? { metadata: source.subject.metadata } : {}),
  };
}

function nextSource(source: RepairSource, candidate: PersistedRepairCandidate, quality: QualityResult): RepairSource {
  return {
    branch_id: source.branch_id,
    expected_branch_head: candidate.artifact_version_id,
    subject: candidateSubject(source, candidate),
    quality,
    constraints: source.constraints,
  };
}

async function loopIdentity(source: RepairSource, policyId: string, policyVersion: string): Promise<string> {
  const hash = await canonicalSha256({
    artifact_version_id: source.subject.artifact_version_id,
    quality_result_id: source.quality.quality_result_id,
    policy_id: policyId,
    policy_version: policyVersion,
  });
  return `repair-loop:${hash}`;
}

export class AutoRepairLoop {
  readonly #ports: AutoRepairPorts;
  readonly #options: AutoRepairRunOptions;
  readonly #now: () => string;

  constructor(ports: AutoRepairPorts, options: AutoRepairRunOptions) {
    if (
      !Number.isInteger(options.policy.max_auto_repair_iterations) ||
      options.policy.max_auto_repair_iterations < 1 ||
      options.policy.max_auto_repair_iterations > 10
    ) {
      throw new AutoRepairError("AUTO_REPAIR_INVALID_ITERATION_BOUND");
    }
    if (options.policy.minimum_expected_gain < 0 || options.policy.max_score_regression < 0) {
      throw new AutoRepairError("AUTO_REPAIR_INVALID_QUALITY_POLICY");
    }
    remainingUsd(options.policy.max_repair_cost_usd, "0");
    this.#ports = ports;
    this.#options = options;
    this.#now = options.now ?? (() => new Date().toISOString());
  }

  async run(initial: RepairSource): Promise<RepairLoopResult> {
    const loopId = await loopIdentity(initial, this.#options.policy.policy_id, this.#options.policy.version);
    if (!(await this.#ports.artifacts.isCurrentHead(initial.branch_id, initial.expected_branch_head))) {
      throw new AutoRepairStaleSourceError("AUTO_REPAIR_STALE_SOURCE");
    }

    let current = initial;
    let spent = "0";
    const attempts: RepairAttemptRecord[] = [];
    const attempted = new Set<string>();
    let lastReasons: readonly string[] = [];

    for (let iteration = 1; iteration <= this.#options.policy.max_auto_repair_iterations; iteration += 1) {
      if (current.quality.status === "PASS" || current.quality.status === "PASS_WITH_WARNINGS") {
        return this.#result(loopId, "SUCCEEDED", initial, current, iteration - 1, spent, attempts, ["QUALITY_ALREADY_PASSED"]);
      }
      if (current.quality.status === "REVIEW_REQUIRED") {
        return this.#result(loopId, "REVIEW_REQUIRED", initial, current, iteration - 1, spent, attempts, ["SOURCE_REVIEW_REQUIRED"]);
      }
      if (!(await this.#ports.artifacts.isCurrentHead(current.branch_id, current.expected_branch_head))) {
        return this.#result(loopId, "STALE_SOURCE", initial, current, iteration - 1, spent, attempts, ["BRANCH_HEAD_CHANGED"]);
      }

      const plan = await buildRepairPlan({
        loop_id: loopId,
        iteration,
        source: current,
        policy: this.#options.policy,
        attempted_fingerprints: attempted,
        ...(this.#ports.cost_estimator ? { estimator: this.#ports.cost_estimator } : {}),
      });
      const item = await this.#selectExecutable(plan.items, current, spent);
      if (!item) {
        const budgetBlocked = plan.items.some((value) => value.paid);
        return this.#result(
          loopId,
          budgetBlocked ? "BUDGET_EXHAUSTED" : "NO_SAFE_REPAIR",
          initial,
          current,
          iteration - 1,
          spent,
          attempts,
          budgetBlocked ? ["REPAIR_BUDGET_UNAVAILABLE"] : ["NO_UNATTEMPTED_SAFE_REPAIR"],
        );
      }
      attempted.add(item.fingerprint);
      if (item.kind === "MANUAL_REVIEW") {
        return this.#result(loopId, "REVIEW_REQUIRED", initial, current, iteration - 1, spent, attempts, item.reason_codes.length ? item.reason_codes : ["MANUAL_REVIEW_REQUIRED"]);
      }

      let reservation: BudgetReservation | null = null;
      let materialization: CandidateMaterialization;
      try {
        if (item.paid) {
          if (!this.#ports.budget) {
            return this.#result(loopId, "BUDGET_EXHAUSTED", initial, current, iteration - 1, spent, attempts, ["BUDGET_PORT_UNAVAILABLE"]);
          }
          reservation = await this.#ports.budget.reserve({
            loop_id: loopId,
            iteration,
            item_id: item.item_id,
            amount_usd: item.estimated_cost_usd,
            source: current,
          });
        }
        materialization = item.kind === "STRUCTURAL_DESIGN_OP"
          ? await executeStructuralRepair(item, current, this.#ports.structural_materializer)
          : await this.#executeGenerative(item, current, reservation);
      } catch (error) {
        if (reservation) await this.#ports.budget!.release(reservation, "REPAIR_EXECUTION_FAILED");
        const reasons = [error instanceof Error ? error.message : "REPAIR_EXECUTION_FAILED"];
        const record = this.#attemptRecord(loopId, iteration, item, current, "0", "REJECTED", reasons);
        attempts.push(record);
        await this.#ports.attempts.append(record);
        lastReasons = reasons;
        continue;
      }

      if (reservation) {
        try {
          await this.#ports.budget!.settle(reservation, materialization.actual_cost_usd);
        } catch {
          spent = addUsd(spent, materialization.actual_cost_usd);
          const reasons = ["AUTO_REPAIR_BUDGET_SETTLEMENT_UNCERTAIN"];
          const record = this.#attemptRecord(loopId, iteration, item, current, materialization.actual_cost_usd, "REJECTED", reasons);
          attempts.push(record);
          await this.#ports.attempts.append(record);
          return this.#result(loopId, "FAILED", initial, current, iteration, spent, attempts, reasons);
        }
      }
      spent = addUsd(spent, materialization.actual_cost_usd);

      const candidateHash = await canonicalSha256({
        loop_id: loopId,
        iteration,
        item: item.fingerprint,
        source: current.subject.artifact_version_id,
        content_hash: materialization.content_hash,
      });
      const candidate = await this.#ports.artifacts.persistCandidate({
        candidate_id: `repair-candidate:${candidateHash}`,
        loop_id: loopId,
        iteration,
        item,
        source: current,
        materialization,
      });
      const quality = await this.#ports.quality.evaluate(candidateSubject(current, candidate), {
        profile_id: current.quality.profile_id,
        profile_version: current.quality.profile_version,
      });
      const comparison = compareQuality(current.quality, quality, this.#options.policy);
      const record: RepairAttemptRecord = {
        ...this.#attemptRecord(loopId, iteration, item, current, materialization.actual_cost_usd, comparison.disposition, comparison.reason_codes),
        candidate_artifact_version_id: candidate.artifact_version_id,
        candidate_quality_result_id: quality.quality_result_id,
        after_score: quality.overall_score,
        score_gain: comparison.score_gain,
      };
      attempts.push(record);
      await this.#ports.attempts.append(record);
      lastReasons = comparison.reason_codes;

      if (comparison.disposition === "REVIEW") {
        await this.#ports.artifacts.rejectCandidate(candidate, comparison.reason_codes);
        return this.#result(loopId, "REVIEW_REQUIRED", initial, current, iteration, spent, attempts, comparison.reason_codes);
      }
      if (comparison.disposition === "REJECTED") {
        await this.#ports.artifacts.rejectCandidate(candidate, comparison.reason_codes);
        continue;
      }

      try {
        await this.#ports.artifacts.promoteCandidate({
          candidate,
          expected_head: current.expected_branch_head,
          target_status: comparison.disposition === "PROMOTED_READY" ? "READY" : "DRAFT",
          quality,
        });
      } catch (error) {
        await this.#ports.artifacts.rejectCandidate(candidate, ["BRANCH_HEAD_CHANGED"]);
        return this.#result(
          loopId,
          "STALE_SOURCE",
          initial,
          current,
          iteration,
          spent,
          attempts,
          [error instanceof Error ? error.message : "BRANCH_HEAD_CHANGED"],
        );
      }
      current = nextSource(current, candidate, quality);
      if (comparison.disposition === "PROMOTED_READY") {
        return this.#result(loopId, "SUCCEEDED", initial, current, iteration, spent, attempts, comparison.reason_codes);
      }
    }

    return this.#result(
      loopId,
      "ITERATION_LIMIT",
      initial,
      current,
      this.#options.policy.max_auto_repair_iterations,
      spent,
      attempts,
      lastReasons.length ? lastReasons : ["MAX_REPAIR_ITERATIONS_REACHED"],
    );
  }

  async #selectExecutable(items: readonly RepairPlanItem[], source: RepairSource, spent: string): Promise<RepairPlanItem | null> {
    const loopRemaining = remainingUsd(this.#options.policy.max_repair_cost_usd, spent);
    for (const item of items) {
      if (!item.paid) return item;
      if (!this.#ports.budget || !canAfford(loopRemaining, item.estimated_cost_usd)) continue;
      const externalRemaining = await this.#ports.budget.remaining(source);
      if (canAfford(externalRemaining, item.estimated_cost_usd)) return item;
    }
    return null;
  }

  async #executeGenerative(item: RepairPlanItem, source: RepairSource, reservation: BudgetReservation | null): Promise<CandidateMaterialization> {
    if (!this.#ports.generative) throw new AutoRepairError("AUTO_REPAIR_GENERATIVE_PORT_UNAVAILABLE");
    if (!reservation) throw new AutoRepairError("AUTO_REPAIR_PAID_REPAIR_WITHOUT_RESERVATION");
    return this.#ports.generative.execute(item, source, reservation.reservation_id);
  }

  #attemptRecord(
    loopId: string,
    iteration: number,
    item: RepairPlanItem,
    source: RepairSource,
    cost: string,
    disposition: RepairAttemptRecord["disposition"],
    reasons: readonly string[],
  ): RepairAttemptRecord {
    return {
      loop_id: loopId,
      iteration,
      plan_item_id: item.item_id,
      action_kind: item.kind,
      source_artifact_version_id: source.subject.artifact_version_id,
      source_quality_result_id: source.quality.quality_result_id,
      before_score: source.quality.overall_score,
      cost_usd: cost,
      disposition,
      reason_codes: [...reasons],
      created_at: this.#now(),
    };
  }

  #result(
    loopId: string,
    status: RepairLoopResult["status"],
    initial: RepairSource,
    current: RepairSource,
    iterations: number,
    spent: string,
    attempts: readonly RepairAttemptRecord[],
    reasons: readonly string[],
  ): RepairLoopResult {
    return {
      loop_id: loopId,
      status,
      initial_artifact_version_id: initial.subject.artifact_version_id,
      final_artifact_version_id: current.subject.artifact_version_id,
      initial_quality_result_id: initial.quality.quality_result_id,
      final_quality_result_id: current.quality.quality_result_id,
      iterations,
      spent_usd: spent,
      attempts: [...attempts],
      reason_codes: [...reasons],
    };
  }
}
