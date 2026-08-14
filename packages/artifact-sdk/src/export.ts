import { artifactManifestSha256 } from "./hashing";
import type {
  ArtifactExportAdapter,
  ArtifactExportFormat,
  ArtifactExportPayload,
  ArtifactExportRequest,
  ArtifactFile,
  ArtifactProvenance,
  ArtifactVersion,
} from "./types";

export class ArtifactExportRegistry {
  readonly #adapters = new Map<ArtifactExportFormat, ArtifactExportAdapter>();

  register(adapter: ArtifactExportAdapter): void {
    if (this.#adapters.has(adapter.format)) throw new Error(`export adapter already registered: ${adapter.format}`);
    this.#adapters.set(adapter.format, adapter);
  }

  async render(request: ArtifactExportRequest): Promise<ArtifactExportPayload> {
    const adapter = this.#adapters.get(request.format);
    if (!adapter) throw new Error(`export adapter unavailable: ${request.format}`);
    return adapter.render(request);
  }
}

export async function buildArtifactExportManifest(
  version: ArtifactVersion,
  provenance: ArtifactProvenance,
  files: readonly ArtifactFile[],
): Promise<Readonly<Record<string, unknown>>> {
  if (version.id !== provenance.artifact_version_id) throw new Error("provenance/version mismatch");
  if (version.organization_id !== provenance.organization_id) throw new Error("provenance tenant mismatch");
  if (
    provenance.brand_rule_set_version !== undefined
    && version.brand_rule_set_version != null
    && provenance.brand_rule_set_version !== version.brand_rule_set_version
  ) {
    throw new Error("brand rule set version mismatch between ArtifactVersion and provenance");
  }
  const brandRuleSetVersion = provenance.brand_rule_set_version ?? version.brand_rule_set_version ?? null;
  return {
    schema_version: "1.0",
    artifact_version_id: version.id,
    artifact_id: version.artifact_id,
    version_number: version.version_number,
    status: version.status,
    content_hash: version.content_hash,
    constraint_snapshot_hash: version.constraint_snapshot_hash,
    brand_rule_set_version: brandRuleSetVersion,
    compiler: provenance.compiler ?? null,
    code_git_sha: provenance.code_git_sha,
    files: [...files]
      .filter((file) => file.artifact_version_id === version.id)
      .sort((a, b) => a.id.localeCompare(b.id))
      .map((file) => ({ id: file.id, role: file.role, mime_type: file.mime_type, size_bytes: file.size_bytes, checksum_sha256: file.checksum_sha256 })),
    manifest_sha256: await artifactManifestSha256(version, provenance, files),
  };
}
