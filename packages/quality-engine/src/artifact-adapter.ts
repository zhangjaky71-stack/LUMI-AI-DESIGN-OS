import { ArtifactEngine } from "../../artifact-sdk/src/engine";
import type { QualityArtifactPort } from "./ports";
import type { QualityResult } from "./types";

export interface QualityResultRepository {
  save(result: QualityResult): Promise<void>;
  get(organizationId: string, qualityResultId: string): Promise<QualityResult | null>;
}

/**
 * NODE-42 boundary: persist the full QualityResult separately and append only
 * quality metadata to the exact ArtifactVersion. This adapter never changes
 * artifact content, branch heads, or approval status.
 */
export class ArtifactEngineQualityAdapter implements QualityArtifactPort {
  readonly #artifacts: ArtifactEngine;
  readonly #results: QualityResultRepository;

  constructor(args: { readonly artifacts: ArtifactEngine; readonly results: QualityResultRepository }) {
    this.#artifacts = args.artifacts;
    this.#results = args.results;
  }

  async record(result: QualityResult): Promise<void> {
    const artifact = this.#artifacts.artifacts.get(result.artifact_id);
    const version = this.#artifacts.versions.get(result.artifact_version_id);
    if (!artifact || !version || version.artifact_id !== artifact.id) {
      throw new Error("QUALITY_ARTIFACT_VERSION_NOT_FOUND");
    }
    if (artifact.organization_id !== result.organization_id || version.organization_id !== result.organization_id || artifact.project_id !== result.project_id) {
      throw new Error("QUALITY_ARTIFACT_SCOPE_MISMATCH");
    }
    if (version.design_document_version_id !== result.design_document_version_id) {
      throw new Error("QUALITY_ARTIFACT_DESIGN_VERSION_MISMATCH");
    }
    if (!Number.isFinite(result.overall_score) || result.overall_score < 0 || result.overall_score > 100) {
      throw new Error("QUALITY_SCORE_INVALID");
    }
    const existing = await this.#results.get(result.organization_id, result.quality_result_id);
    if (existing) {
      if (existing.artifact_version_id !== result.artifact_version_id || existing.profile_id !== result.profile_id || existing.profile_version !== result.profile_version) {
        throw new Error("QUALITY_RESULT_ID_CONFLICT");
      }
      return;
    }
    await this.#results.save(result);
    this.#artifacts.versions.set(version.id, { ...version, quality_score: result.overall_score / 100 });
  }
}

export class InMemoryQualityResultRepository implements QualityResultRepository {
  readonly results = new Map<string, QualityResult>();

  async save(result: QualityResult): Promise<void> {
    const key = `${result.organization_id}:${result.quality_result_id}`;
    const existing = this.results.get(key);
    if (existing && existing.artifact_version_id !== result.artifact_version_id) throw new Error("QUALITY_RESULT_ID_CONFLICT");
    this.results.set(key, structuredClone(result));
  }

  async get(organizationId: string, qualityResultId: string): Promise<QualityResult | null> {
    const value = this.results.get(`${organizationId}:${qualityResultId}`);
    return value ? structuredClone(value) : null;
  }
}
