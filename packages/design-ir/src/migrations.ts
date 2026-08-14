import type { DesignDocument } from "./types";

export type DesignIrMigration = (document: DesignDocument) => DesignDocument;

export interface MigrationStep {
  readonly from: string;
  readonly to: string;
  readonly migrate: DesignIrMigration;
}

export class DesignIrMigrationRegistry {
  private readonly steps = new Map<string, MigrationStep>();

  register(step: MigrationStep): this {
    if (step.from === step.to) throw new Error("Migration must advance schema_version");
    if (this.steps.has(step.from)) throw new Error(`Migration from ${step.from} is already registered`);
    this.steps.set(step.from, step);
    return this;
  }

  migrate(document: DesignDocument, targetVersion: string): DesignDocument {
    if (document.schema_version === targetVersion) return structuredClone(document);

    let current = structuredClone(document);
    const visited = new Set<string>();
    while (current.schema_version !== targetVersion) {
      if (visited.has(current.schema_version)) {
        throw new Error(`Migration cycle detected at ${current.schema_version}`);
      }
      visited.add(current.schema_version);
      const step = this.steps.get(current.schema_version);
      if (!step) {
        throw new Error(`No Design IR migration path from ${current.schema_version} to ${targetVersion}`);
      }
      const provenance = structuredClone(current.metadata.provenance);
      const migrated = step.migrate(structuredClone(current));
      if (migrated.schema_version !== step.to) {
        throw new Error(`Migration ${step.from} -> ${step.to} returned ${migrated.schema_version}`);
      }
      current =
        provenance !== undefined && migrated.metadata.provenance === undefined
          ? { ...migrated, metadata: { ...migrated.metadata, provenance } }
          : migrated;
    }
    return current;
  }
}

export const designIrMigrations = new DesignIrMigrationRegistry();
