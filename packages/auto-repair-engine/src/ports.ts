import type { CriticSubject, QualityResult } from "../../quality-engine/src/index";
import type {
  AutoRepairPolicy,
  CandidateMaterialization,
  PersistedRepairCandidate,
  RepairAttemptRecord,
  RepairPlanItem,
  RepairSource,
} from "./types";

export interface RepairCostEstimatorPort {
  estimate(item: Omit<RepairPlanItem, "estimated_cost_usd">, source: RepairSource): Promise<string>;
}

export interface StructuralMaterializerPort {
  materialize(document: CandidateMaterialization["design_document"], source: RepairSource): Promise<Omit<CandidateMaterialization, "design_document" | "actual_cost_usd">>;
}

export interface GenerativeRepairPort {
  execute(item: RepairPlanItem, source: RepairSource, reservationId: string): Promise<CandidateMaterialization>;
}

export interface BudgetReservation {
  readonly reservation_id: string;
  readonly amount_usd: string;
}

export interface BudgetReservationPort {
  remaining(source: RepairSource): Promise<string>;
  reserve(input: { readonly loop_id: string; readonly iteration: number; readonly item_id: string; readonly amount_usd: string; readonly source: RepairSource }): Promise<BudgetReservation>;
  settle(reservation: BudgetReservation, actualCostUsd: string): Promise<void>;
  release(reservation: BudgetReservation, reason: string): Promise<void>;
}

export interface RepairArtifactRepository {
  isCurrentHead(branchId: string, expectedHead: string): Promise<boolean>;
  persistCandidate(input: {
    readonly candidate_id: string;
    readonly loop_id: string;
    readonly iteration: number;
    readonly item: RepairPlanItem;
    readonly source: RepairSource;
    readonly materialization: CandidateMaterialization;
  }): Promise<PersistedRepairCandidate>;
  rejectCandidate(candidate: PersistedRepairCandidate, reasonCodes: readonly string[]): Promise<void>;
  promoteCandidate(input: {
    readonly candidate: PersistedRepairCandidate;
    readonly expected_head: string;
    readonly target_status: "DRAFT" | "READY";
    readonly quality: QualityResult;
  }): Promise<void>;
}

export interface RepairQualityPort {
  evaluate(subject: CriticSubject, profile: { readonly profile_id: string; readonly profile_version: string }): Promise<QualityResult>;
}

export interface RepairAttemptRepository {
  append(record: RepairAttemptRecord): Promise<void>;
}

export interface AutoRepairPorts {
  readonly artifacts: RepairArtifactRepository;
  readonly quality: RepairQualityPort;
  readonly attempts: RepairAttemptRepository;
  readonly structural_materializer: StructuralMaterializerPort;
  readonly cost_estimator?: RepairCostEstimatorPort;
  readonly budget?: BudgetReservationPort;
  readonly generative?: GenerativeRepairPort;
}

export interface AutoRepairRunOptions {
  readonly policy: AutoRepairPolicy;
  readonly now?: () => string;
}
