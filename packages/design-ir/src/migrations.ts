import { canonicalize } from "./canonical";
import { IrRuntimeError, type DesignDocument, type MigrationStep } from "./types";
import { parseDocument } from "./validation";

function recordMigration(
  document: DesignDocument,
  from: string,
  to: string,
): DesignDocument {
  const provenance = document.metadata.migration_provenance;
  const current = Array.isArray(provenance) ? provenance : [];
  return {
    ...structuredClone(document),
    schema_version: to,
    metadata: {
      ...structuredClone(document.metadata),
      migration_provenance: [
        ...current,
        {
          from,
          to,
          source_canonical: canonicalize(document),
        },
      ],
    },
  };
}

export const MIGRATIONS: readonly MigrationStep[] = [
  {
    from: "1.0",
    to: "1.1",
    migrate: (document) => recordMigration(document, "1.0", "1.1"),
  },
  {
    from: "1.1",
    to: "2.0",
    migrate: (document) => recordMigration(document, "1.1", "2.0"),
  },
];

export function migrate(document: DesignDocument, targetVersion: string): DesignDocument {
  let current = parseDocument(document);
  const seen = new Set<string>();
  while (current.schema_version !== targetVersion) {
    if (seen.has(current.schema_version)) {
      throw new IrRuntimeError({
        code: "IR_VERSION_UNSUPPORTED",
        message: `migration cycle from ${current.schema_version}`,
      });
    }
    seen.add(current.schema_version);
    const step = MIGRATIONS.find((candidate) => candidate.from === current.schema_version);
    if (!step) {
      throw new IrRuntimeError({
        code: "IR_VERSION_UNSUPPORTED",
        message: `no migration path from ${current.schema_version} to ${targetVersion}`,
      });
    }
    current = parseDocument(step.migrate(current));
  }
  return current;
}
