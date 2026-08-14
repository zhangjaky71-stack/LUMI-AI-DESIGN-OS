import { ArtifactEngine } from "./engine";
import type { ExportArtifactPort, ExportFileRecord, ExportJob } from "./export-engine-types";
import type { ArtifactFileRole, ArtifactObjectStore, ArtifactType } from "./types";

const GIT_SHA = /^[0-9a-f]{40}$/;

function artifactType(file: ExportFileRecord): ArtifactType {
  if (file.mime_type === "application/pdf") return "PDF";
  if (file.mime_type === "image/svg+xml") return "VECTOR_IMAGE";
  if (file.mime_type.startsWith("image/")) return "RASTER_IMAGE";
  if (file.mime_type === "application/zip" || file.mime_type === "application/json") return "EXPORT_PACKAGE";
  return "ARCHIVE";
}

function fileRole(file: ExportFileRecord): ArtifactFileRole {
  if (file.mime_type === "application/pdf") return "PRINT_PDF";
  if (file.mime_type === "application/json") return "LAYER_DATA";
  return "ORIGINAL";
}

function ids(job: ExportJob, file: ExportFileRecord): {
  artifact: string;
  branch: string;
  version: string;
  file: string;
  edge: string;
} {
  const base = `${job.export_fingerprint}:${file.variant_id}:${file.checksum_sha256}`;
  return {
    artifact: `artifact:export:${base}`,
    branch: `artifact-branch:export:${base}`,
    version: `artifact-version:export:${base}`,
    file: `artifact-file:export:${base}`,
    edge: `artifact-edge:export:${base}`,
  };
}

export class ArtifactEngineExportAdapter implements ExportArtifactPort {
  readonly #engine: ArtifactEngine;
  readonly #store: ArtifactObjectStore;
  readonly #codeGitSha: string;

  constructor(args: { readonly engine: ArtifactEngine; readonly store: ArtifactObjectStore; readonly code_git_sha: string }) {
    if (!GIT_SHA.test(args.code_git_sha)) throw new Error("EXPORT_CODE_GIT_SHA_INVALID");
    this.#engine = args.engine;
    this.#store = args.store;
    this.#codeGitSha = args.code_git_sha;
  }

  async persistExport(args: Parameters<ExportArtifactPort["persistExport"]>[0]): Promise<void> {
    const { job, manifest } = args;
    const source = this.#engine.versions.get(job.source.artifact_version_id);
    if (!source || source.organization_id !== job.organization_id || source.artifact_id !== job.source.artifact_id) {
      throw new Error("EXPORT_SOURCE_ARTIFACT_VERSION_NOT_IN_HISTORY");
    }
    if (source.content_hash !== job.source.content_hash || source.constraint_snapshot_hash !== job.source.constraint_snapshot_hash) {
      throw new Error("EXPORT_SOURCE_ARTIFACT_SNAPSHOT_MISMATCH");
    }
    const outputs = [...args.files, ...(job.manifest_file ? [job.manifest_file] : [])];
    for (const output of outputs) {
      const identity = ids(job, output);
      if (this.#engine.versions.has(identity.version)) continue;
      this.#engine.addArtifact({
        id: identity.artifact,
        organization_id: job.organization_id,
        project_id: job.project_id,
        type: artifactType(output),
        title: output.filename,
        archived: false,
      });
      this.#engine.addBranch({
        id: identity.branch,
        organization_id: job.organization_id,
        artifact_id: identity.artifact,
        name: "main",
        base_version_id: null,
        head_version_id: null,
        created_by: job.spec.requested_by,
      });
      this.#engine.addVersion({
        id: identity.version,
        organization_id: job.organization_id,
        artifact_id: identity.artifact,
        branch_id: identity.branch,
        parent_version_id: null,
        schema_version: "export-output.v1",
        version_number: 1,
        status: "DRAFT",
        content_hash: output.checksum_sha256,
        constraint_snapshot_hash: job.source.constraint_snapshot_hash,
        created_by_type: "USER",
        created_by_id: job.spec.requested_by,
        created_at: job.created_at,
        primary_file_id: identity.file,
        design_document_version_id: job.source.design_document_version_id,
        brand_rule_set_version: job.source.brand_rule_set_version ?? null,
      }, null);
      await this.#engine.attachVerifiedFile({
        id: identity.file,
        organization_id: job.organization_id,
        artifact_version_id: identity.version,
        role: fileRole(output),
        storage_key: output.storage_key,
        mime_type: output.mime_type,
        size_bytes: output.size_bytes,
        checksum_sha256: output.checksum_sha256,
        ...(output.width !== undefined ? { width: output.width } : {}),
        ...(output.height !== undefined ? { height: output.height } : {}),
        metadata: {
          export_job_id: job.export_job_id,
          export_fingerprint: job.export_fingerprint,
          export_variant_id: output.variant_id,
          manifest_sha256: manifest.manifest_sha256,
          ...(output.page_count !== undefined ? { page_count: output.page_count } : {}),
        },
      }, this.#store);
      this.#engine.addProvenance({
        artifact_version_id: identity.version,
        organization_id: job.organization_id,
        constraint_snapshot_hash: job.source.constraint_snapshot_hash,
        code_git_sha: this.#codeGitSha,
        compiler: job.source.compiler_provenance,
        ...(job.source.brand_rule_set_version ? { brand_rule_set_version: job.source.brand_rule_set_version } : {}),
        input_artifact_version_ids: [job.source.artifact_version_id],
        recipe_version: `export-engine:${manifest.export_engine_version}`,
      });
      this.#engine.addEdge({
        id: identity.edge,
        organization_id: job.organization_id,
        from_version_id: job.source.artifact_version_id,
        to_version_id: identity.version,
        type: "EXPORTED_FROM",
        metadata: {
          export_job_id: job.export_job_id,
          variant_id: output.variant_id,
          export_fingerprint: job.export_fingerprint,
          manifest_sha256: manifest.manifest_sha256,
        },
      });
      this.#engine.transition(identity.version, "READY");
    }
  }
}
