import { canonicalSha256, canonicalStringify } from "../../design-ir/src/index";
import type { ArtifactFile, ArtifactProvenance, ArtifactVersion, CompilerArtifactProvenance } from "./types";

function compilerIdentity(value: CompilerArtifactProvenance | undefined): unknown {
  if (!value) return null;
  return {
    compiler_version: value.compiler_version,
    document_id: value.document_id,
    schema_version: value.schema_version,
    document_version: value.document_version,
    resource_versions: value.resource_versions,
    font_versions: value.font_versions,
    compile_hash: value.compile_hash,
  };
}

export function artifactStableManifest(
  version: Pick<ArtifactVersion, "artifact_id" | "schema_version" | "content_hash" | "constraint_snapshot_hash" | "brand_rule_set_version">,
  provenance: ArtifactProvenance,
  files: readonly ArtifactFile[],
): unknown {
  const brandRuleSetVersion = provenance.brand_rule_set_version ?? version.brand_rule_set_version ?? null;
  if (
    provenance.brand_rule_set_version !== undefined
    && version.brand_rule_set_version != null
    && provenance.brand_rule_set_version !== version.brand_rule_set_version
  ) {
    throw new Error("brand rule set version mismatch between ArtifactVersion and provenance");
  }
  return {
    artifact_id: version.artifact_id,
    schema_version: version.schema_version,
    content_hash: version.content_hash,
    constraint_snapshot_hash: version.constraint_snapshot_hash,
    brand_rule_set_version: brandRuleSetVersion,
    compiler: compilerIdentity(provenance.compiler),
    code_git_sha: provenance.code_git_sha,
    prompt_hash: provenance.prompt_hash ?? null,
    prompt_template_version: provenance.prompt_template_version ?? null,
    recipe_version: provenance.recipe_version ?? null,
    skill_versions: provenance.skill_versions ?? {},
    input_asset_ids: [...new Set(provenance.input_asset_ids ?? [])].sort(),
    input_artifact_version_ids: [...new Set(provenance.input_artifact_version_ids ?? [])].sort(),
    files: [...files]
      .sort((a, b) => a.id.localeCompare(b.id))
      .map((file) => ({
        id: file.id,
        role: file.role,
        storage_key: file.storage_key,
        mime_type: file.mime_type,
        size_bytes: file.size_bytes,
        checksum_sha256: file.checksum_sha256,
        width: file.width ?? null,
        height: file.height ?? null,
        duration_ms: file.duration_ms ?? null,
      })),
  };
}

export async function artifactManifestSha256(
  version: Pick<ArtifactVersion, "artifact_id" | "schema_version" | "content_hash" | "constraint_snapshot_hash" | "brand_rule_set_version">,
  provenance: ArtifactProvenance,
  files: readonly ArtifactFile[],
): Promise<string> {
  return canonicalSha256(artifactStableManifest(version, provenance, files));
}

export function contentAddressedObjectKey(
  organizationId: string,
  checksumSha256: string,
  extension: string,
): string {
  if (!/^[0-9a-f]{64}$/.test(checksumSha256)) throw new Error("checksum must be lowercase SHA-256");
  const safeExt = extension.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 10) || "bin";
  return `org/${organizationId}/artifacts/sha256/${checksumSha256.slice(0, 2)}/${checksumSha256}.${safeExt}`;
}

export function canonicalArtifactJson(value: unknown): string {
  return canonicalStringify(value);
}
