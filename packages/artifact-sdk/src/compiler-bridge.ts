import type { CompiledSceneSnapshot } from "../../canvas-sdk/src/index";
import type { CompilerArtifactProvenance } from "./types";

export function compilerProvenanceFromSnapshot(snapshot: CompiledSceneSnapshot): CompilerArtifactProvenance {
  const value = snapshot.provenance;
  if (!value.compile_hash) throw new Error("compiled artifact requires NODE-41 compile_hash");
  return {
    compiler_version: value.compiler_version,
    document_id: value.document_id,
    schema_version: value.schema_version,
    document_version: value.document_version,
    resource_versions: { ...value.resource_versions },
    font_versions: { ...value.font_versions },
    compile_hash: value.compile_hash,
  };
}
