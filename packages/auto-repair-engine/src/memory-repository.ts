import { canonicalSha256 } from "../../design-ir/src/index";
import type { RepairArtifactRepository } from "./ports";
import type { PersistedRepairCandidate, RepairAttemptRecord, RepairPlanItem } from "./types";

export type MemoryCandidateStatus = "DRAFT" | "READY" | "REJECTED";

export interface MemoryRepairCandidateRecord {
  readonly candidate: PersistedRepairCandidate;
  readonly item: RepairPlanItem;
  readonly loop_id: string;
  readonly iteration: number;
  readonly source_artifact_version_id: string;
  readonly lineage_type: "EDITED_FROM";
  readonly lineage_metadata: Readonly<Record<string, unknown>>;
  readonly status: MemoryCandidateStatus;
  readonly quality_result_id?: string;
  readonly rejection_reason_codes?: readonly string[];
}

async function deterministicUuid(value: string): Promise<string> {
  const hash = await canonicalSha256(value);
  return `${hash.slice(0, 8)}-${hash.slice(8, 12)}-4${hash.slice(13, 16)}-8${hash.slice(17, 20)}-${hash.slice(20, 32)}`;
}

export class MemoryRepairArtifactRepository implements RepairArtifactRepository {
  readonly heads = new Map<string, string>();
  readonly candidates = new Map<string, MemoryRepairCandidateRecord>();
  readonly events: string[] = [];

  constructor(branchId: string, headVersionId: string) {
    this.heads.set(branchId, headVersionId);
  }

  async isCurrentHead(branchId: string, expectedHead: string): Promise<boolean> {
    this.events.push(`head-check:${branchId}:${expectedHead}`);
    return this.heads.get(branchId) === expectedHead;
  }

  async persistCandidate(input: Parameters<RepairArtifactRepository["persistCandidate"]>[0]): Promise<PersistedRepairCandidate> {
    this.events.push(`persist:${input.candidate_id}`);
    const existing = this.candidates.get(input.candidate_id);
    if (existing) return existing.candidate;
    const artifactVersionId = await deterministicUuid(`${input.candidate_id}:artifact`);
    const designVersionId = await deterministicUuid(`${input.candidate_id}:design`);
    const candidate: PersistedRepairCandidate = {
      ...input.materialization,
      artifact_version_id: artifactVersionId,
      design_document_version_id: designVersionId,
      branch_id: input.source.branch_id,
      source_artifact_version_id: input.source.subject.artifact_version_id,
    };
    this.candidates.set(input.candidate_id, {
      candidate,
      item: input.item,
      loop_id: input.loop_id,
      iteration: input.iteration,
      source_artifact_version_id: input.source.subject.artifact_version_id,
      lineage_type: "EDITED_FROM",
      lineage_metadata: {
        repair_loop_id: input.loop_id,
        repair_item_id: input.item.item_id,
        repair_action_kind: input.item.kind,
        source_quality_result_id: input.source.quality.quality_result_id,
      },
      status: "DRAFT",
    });
    return candidate;
  }

  async rejectCandidate(candidate: PersistedRepairCandidate, reasonCodes: readonly string[]): Promise<void> {
    this.events.push(`reject:${candidate.artifact_version_id}`);
    const [key, entry] = this.entryFor(candidate);
    this.candidates.set(key, { ...entry, status: "REJECTED", rejection_reason_codes: [...reasonCodes] });
  }

  async promoteCandidate(input: Parameters<RepairArtifactRepository["promoteCandidate"]>[0]): Promise<void> {
    this.events.push(`promote:${input.candidate.artifact_version_id}:${input.target_status}`);
    const current = this.heads.get(input.candidate.branch_id);
    if (current !== input.expected_head) throw new Error("AUTO_REPAIR_BRANCH_HEAD_CAS_CONFLICT");
    const [key, entry] = this.entryFor(input.candidate);
    this.candidates.set(key, { ...entry, status: input.target_status, quality_result_id: input.quality.quality_result_id });
    this.heads.set(input.candidate.branch_id, input.candidate.artifact_version_id);
  }

  simulateExternalHead(branchId: string, versionId: string): void {
    this.events.push(`external-head:${branchId}:${versionId}`);
    this.heads.set(branchId, versionId);
  }

  recordByArtifactVersion(artifactVersionId: string): MemoryRepairCandidateRecord | undefined {
    return [...this.candidates.values()].find((entry) => entry.candidate.artifact_version_id === artifactVersionId);
  }

  private entryFor(candidate: PersistedRepairCandidate): readonly [string, MemoryRepairCandidateRecord] {
    for (const entry of this.candidates) {
      if (entry[1].candidate.artifact_version_id === candidate.artifact_version_id) return entry;
    }
    throw new Error("AUTO_REPAIR_CANDIDATE_NOT_FOUND");
  }
}

export class MemoryRepairAttemptRepository {
  readonly records: RepairAttemptRecord[] = [];
  readonly events: string[];

  constructor(events: string[] = []) {
    this.events = events;
  }

  async append(record: RepairAttemptRecord): Promise<void> {
    this.events.push(`attempt:${record.iteration}:${record.disposition}`);
    this.records.push(structuredClone(record));
  }
}
